"""
agent.py

The FitFindr planning loop. Orchestrates the three tools in response to a
natural language user query, passing state between them via a session dict.

Complete tools.py and test each tool in isolation before implementing this file.

Usage (once implemented):
    from agent import run_agent
    from utils.data_loader import get_example_wardrobe

    result = run_agent(
        query="vintage graphic tee under $30, size M",
        wardrobe=get_example_wardrobe(),
    )
    print(result["fit_card"])
    print(result["error"])   # None on success
"""

import re

from tools import search_listings, suggest_outfit, create_fit_card


# ── session state ─────────────────────────────────────────────────────────────

def _new_session(query: str, wardrobe: dict) -> dict:
    """
    Initialize and return a fresh session dict for one user interaction.

    The session dict is the single source of truth for everything that happens
    during a run — it stores the original query, parsed parameters, tool results,
    and any error that caused early termination.

    You may add fields to this dict as needed for your implementation.
    """
    return {
        "query": query,              # original user query
        "parsed": {},                # extracted description / size / max_price
        "search_results": [],        # list of matching listing dicts
        "selected_item": None,       # top result, passed into suggest_outfit
        "wardrobe": wardrobe,        # user's wardrobe dict
        "outfit_suggestion": None,   # string returned by suggest_outfit
        "fit_card": None,            # string returned by create_fit_card
        "error": None,               # set if the interaction ended early
    }


# ── query parser ─────────────────────────────────────────────────────────────

def _parse_query(query: str) -> dict:
    """
    Parse a free-text user query into structured search filters using regex.

    Extracts:
        description (str)       – the clothing item / search phrase
        size        (str|None)  – e.g. "M", "S/M", "W28", "US 8"
        max_price   (float|None)– ceiling price in dollars

    Handles phrases like:
        "vintage graphic tee under $30, size M"
        "jacket under 50"
        "size S black boots"
        "max price $25 blouse"
        "90s track jacket in size M"
    """
    text = query.strip()

    # ── 1. Extract max_price ──────────────────────────────────────────────────
    max_price: float | None = None
    price_patterns = [
        # "under $30", "below $30", "max price $25", "max $25", "budget $40"
        r"(?:under|below|max(?:imum)?(?:\s+price)?|budget)\s*\$?\s*(\d+(?:\.\d+)?)",
        # "$30 or less", "$30 limit"
        r"\$\s*(\d+(?:\.\d+)?)\s*(?:or\s+less|max|limit|budget)\b",
    ]
    for pat in price_patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            max_price = float(m.group(1))
            text = text[: m.start()] + " " + text[m.end():]
            break

    # ── 2. Extract size ───────────────────────────────────────────────────────
    size: str | None = None
    size_patterns = [
        # "size M", "size S/M", ", size XL", "in size M", "in a medium"
        r"(?:,\s*|\bin\s+(?:a\s+)?|size\s+)([A-Z]{1,3}(?:/[A-Z]{1,3})?)\b",
        # explicit "size:" prefix
        r"\bsize[d]?\s*:?\s*([A-Za-z0-9]{1,5}(?:/[A-Za-z0-9]{1,5})?)\b",
        # standalone standard sizes
        r"\b(XS|S|M|L|XL|XXL|XXXL|S/M|M/L|L/XL|XL/XXL)\b",
        # waist + optional length: W28, W30 L30
        r"\b(W\d{2}(?:\s*L\d{2})?)\b",
        # US shoe sizes: "US 8", "US 8.5"
        r"\b(US\s*\d+(?:\.\d+)?)\b",
    ]
    for pat in size_patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            size = m.group(1).strip().upper()
            text = text[: m.start()] + " " + text[m.end():]
            break

    # ── 3. Build description from remaining text ──────────────────────────────
    # Drop conversational filler that doesn't describe the item
    filler_patterns = [
        r"i['']?m\s+looking\s+for\s+(?:an?\s+)?",
        r"i\s+(?:want|need|would\s+like)\s+(?:an?\s+)?",
        r"(?:can\s+you\s+)?(?:find|search\s+for|show\s+me)\s+(?:an?\s+)?",
        r"looking\s+for\s+(?:an?\s+)?",
        r"i\s+mostly\s+wear\b.*",        # wardrobe context — irrelevant to search
        r"my\s+(?:usual\s+)?style\s+is\b.*",
        r"[,;\.]+\s*$",                  # trailing punctuation
    ]
    for pat in filler_patterns:
        text = re.sub(pat, " ", text, flags=re.IGNORECASE)

    description = " ".join(text.split()).strip()

    # Last-resort: if description is still empty, use the raw query
    if not description:
        description = query.strip()

    return {
        "description": description,
        "size": size,
        "max_price": max_price,
    }


# ── no-results error message ──────────────────────────────────────────────────

def _no_results_message(description: str, size: str | None, max_price: float | None) -> str:
    """Return a specific, actionable no-results message."""
    parts = [f'No listings found for "{description}"']
    if size:
        parts.append(f"with size {size}")
    if max_price is not None:
        parts.append(f"under ${max_price:g}")
    base = " ".join(parts) + "."

    tips = []
    if size:
        tips.append("remove the size filter")
    if max_price is not None:
        tips.append("raise your price limit")

    # Suggest 1-2 shorter keywords from the description
    words = [w for w in description.lower().split() if len(w) > 3]
    if words:
        keyword_examples = " or ".join(f'"{w}"' for w in words[:2])
        tips.append(f"use broader keywords like {keyword_examples}")
    else:
        tips.append('use broader keywords like "top" or "jacket"')

    suggestion = "Try: " + ", ".join(tips) + "."
    return f"{base} {suggestion}"


# ── planning loop ─────────────────────────────────────────────────────────────

def run_agent(query: str, wardrobe: dict) -> dict:
    """
    Main agent entry point. Runs the FitFindr planning loop for a single
    user interaction and returns the completed session dict.

    Args:
        query:    Natural language user request
                  (e.g., "vintage graphic tee under $30, size M")
        wardrobe: User's wardrobe dict — use get_example_wardrobe() or
                  get_empty_wardrobe() from utils/data_loader.py

    Returns:
        The session dict after the interaction completes. Check session["error"]
        first — if it is not None, the interaction ended early and the other
        output fields (outfit_suggestion, fit_card) will be None.

    TODO — implement this function using the planning loop you designed in planning.md:

        Step 1: Initialize the session with _new_session().

        Step 2: Parse the user's query to extract a description, size, and
                max_price. You can use regex, string splitting, or ask the LLM
                to parse it — document your choice in planning.md.
                Store the result in session["parsed"].

        Step 3: Call search_listings() with the parsed parameters.
                Store results in session["search_results"].
                If no results: set session["error"] to a helpful message and
                return the session early. Do NOT proceed to suggest_outfit
                with empty input.

        Step 4: Select the item to use (e.g., the top result).
                Store it in session["selected_item"].

        Step 5: Call suggest_outfit() with the selected item and wardrobe.
                Store the result in session["outfit_suggestion"].

        Step 6: Call create_fit_card() with the outfit suggestion and selected item.
                Store the result in session["fit_card"].

        Step 7: Return the session.

    Before writing code, complete the Planning Loop and State Management sections
    of planning.md — your implementation should match what you described there.
    """
    # ── Step 1: initialise session ────────────────────────────────────────────
    session = _new_session(query, wardrobe)

    # ── Step 2: parse query ───────────────────────────────────────────────────
    parsed = _parse_query(query)
    session["parsed"] = parsed

    description = parsed["description"]
    size        = parsed["size"]
    max_price   = parsed["max_price"]

    # Guard: unparseable / blank description
    if not description or not description.strip():
        session["error"] = (
            "I need an item description to search. "
            "Try something like 'vintage graphic tee under $30' or 'black loafers size 8'."
        )
        return session

    # ── Step 3: search listings ───────────────────────────────────────────────
    results = search_listings(description, size=size, max_price=max_price)
    session["search_results"] = results

    # ── Step 4: branch on empty results ──────────────────────────────────────
    if not results:
        session["error"] = _no_results_message(description, size, max_price)
        # selected_item, outfit_suggestion, fit_card all remain None
        return session

    # ── Step 5: select top result ─────────────────────────────────────────────
    session["selected_item"] = results[0]

    # ── Step 6: suggest outfit ────────────────────────────────────────────────
    session["outfit_suggestion"] = suggest_outfit(
        session["selected_item"], session["wardrobe"]
    )

    # ── Step 7: create fit card ───────────────────────────────────────────────
    session["fit_card"] = create_fit_card(
        session["outfit_suggestion"], session["selected_item"]
    )

    # ── Step 8: return completed session ─────────────────────────────────────
    return session


# ── CLI test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from utils.data_loader import get_example_wardrobe, get_empty_wardrobe

    print("=== Happy path: graphic tee ===\n")
    session = run_agent(
        query="looking for a vintage graphic tee under $30",
        wardrobe=get_example_wardrobe(),
    )
    if session["error"]:
        print(f"Error: {session['error']}")
    else:
        print(f"Found: {session['selected_item']['title']}")
        print(f"\nOutfit: {session['outfit_suggestion']}")
        print(f"\nFit card: {session['fit_card']}")

    print("\n\n=== No-results path ===\n")
    session2 = run_agent(
        query="designer ballgown size XXS under $5",
        wardrobe=get_example_wardrobe(),
    )
    print(f"Error message: {session2['error']}")
