"""
tools.py

The three required FitFindr tools. Each tool is a standalone function that
can be called and tested independently before being wired into the agent loop.

Tools:
    search_listings(description, size, max_price)  → list[dict]
    suggest_outfit(new_item, wardrobe)              → str
    create_fit_card(outfit, new_item)               → str
"""

import os
import re

from dotenv import load_dotenv

from utils.data_loader import load_listings

load_dotenv()

# ── Stopwords to ignore when tokenizing the user query ────────────────────────

_STOPWORDS = {
    "the", "a", "an", "for", "under", "with", "and", "size",
    "looking", "i", "in", "at", "of", "to", "is", "its", "it",
    "me", "my", "on", "or", "that", "this",
}


# ── Groq client (lazy, returns None if key missing) ───────────────────────────

def _get_groq_client():
    """
    Return a Groq client if GROQ_API_KEY is set, otherwise return None.
    Never raises — callers must handle the None case as a fallback signal.
    """
    try:
        from groq import Groq
        api_key = os.environ.get("GROQ_API_KEY", "").strip()
        if not api_key:
            return None
        return Groq(api_key=api_key)
    except Exception:
        return None


def _groq_chat(prompt: str, temperature: float = 0.7) -> str | None:
    """
    Make a single-turn Groq chat completion.
    Returns the response text, or None if the call fails for any reason.
    """
    client = _get_groq_client()
    if client is None:
        return None
    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1000,
            temperature=temperature,
        )
        return response.choices[0].message.content.strip()
    except Exception:
        return None


# ── Tokenizer helper ──────────────────────────────────────────────────────────

def _tokenize(text: str) -> set[str]:
    """Lowercase alphanumeric tokenization — punctuation is ignored."""
    if not text:
        return set()
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def _tokenize_query(text: str) -> set[str]:
    """Tokenize a user query and remove stopwords."""
    return _tokenize(text) - _STOPWORDS


def _listing_tokens(listing: dict) -> set[str]:
    """
    Build the full searchable token set for a listing from all relevant fields.
    Excludes 'id', 'price', and 'size' (those are filters, not ranking signals).
    """
    parts: list[str] = []
    for field in ("title", "description", "category", "condition", "brand", "platform"):
        val = listing.get(field)
        if val:
            parts.append(str(val))
    for field in ("style_tags", "colors"):
        val = listing.get(field)
        if isinstance(val, list):
            parts.extend(str(v) for v in val)
    return _tokenize(" ".join(parts))


# ── Tool 1: search_listings ───────────────────────────────────────────────────

def search_listings(
    description: str,
    size: str | None = None,
    max_price: float | None = None,
) -> list[dict]:
    """
    Search the mock listings dataset for items matching the description,
    optional size, and optional price ceiling.

    Args:
        description: Keywords describing what the user is looking for.
        size:        Size string to filter by, or None to skip size filtering.
                     Matching is case-insensitive; "M" matches "M" or "S/M".
        max_price:   Maximum price (inclusive), or None to skip price filtering.

    Returns:
        A list of matching listing dicts sorted by relevance (best match first).
        Returns [] if nothing matches — never raises.
    """
    try:
        listings = load_listings()
    except Exception:
        return []

    # ── Step 1: hard filters ──────────────────────────────────────────────────

    # Price filter (inclusive)
    if max_price is not None:
        listings = [l for l in listings if l.get("price", 0) <= max_price]

    # Size filter — case-insensitive substring match against listing size field
    if size is not None:
        size_query = size.strip().lower()
        filtered = []
        for l in listings:
            listing_size = str(l.get("size", "")).lower()
            # Allow "M" to match "M", "S/M", "M/L", etc.
            # Split the listing size on "/" and check each part, plus check full string
            size_parts = [p.strip() for p in re.split(r"[/\s,]+", listing_size)]
            if size_query in size_parts or size_query in listing_size:
                filtered.append(l)
        listings = filtered

    # ── Step 2: keyword scoring ───────────────────────────────────────────────

    query_tokens = _tokenize_query(description)
    if not query_tokens:
        # No meaningful query tokens — return filtered listings unsorted
        return listings

    scored: list[tuple[int, float, int, dict]] = []
    for original_index, listing in enumerate(listings):
        listing_toks = _listing_tokens(listing)
        score = len(query_tokens & listing_toks)
        if score == 0:
            continue
        price = listing.get("price", 0.0)
        # Tuple: (-score, price, original_index) → sorts highest score first,
        # then lower price first, then stable original order.
        scored.append((-score, price, original_index, listing))

    scored.sort(key=lambda x: (x[0], x[1], x[2]))

    return [entry[3] for entry in scored]


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

def suggest_outfit(new_item: dict, wardrobe: dict) -> str:
    """
    Given a thrifted item and the user's wardrobe, suggest 1–2 complete outfits.

    Args:
        new_item: A listing dict (the item the user is considering buying).
        wardrobe: A wardrobe dict with an 'items' list. May be empty.

    Returns:
        A non-empty readable string with outfit suggestions. Never raises.
    """
    # ── Build item description string for the prompt ──────────────────────────
    title = new_item.get("title", "this item")
    category = new_item.get("category", "")
    style_tags = new_item.get("style_tags", [])
    colors = new_item.get("colors", [])
    condition = new_item.get("condition", "")
    platform = new_item.get("platform", "")
    price = new_item.get("price", "")

    tags_str = ", ".join(style_tags) if style_tags else "versatile"
    colors_str = ", ".join(colors) if colors else "neutral"

    item_summary = (
        f'"{title}" — a {category} in {colors_str}, tagged as {tags_str}. '
        f'Condition: {condition}. From {platform}, priced at ${price}.'
    )

    # ── Wardrobe items ────────────────────────────────────────────────────────
    wardrobe_items: list[dict] = wardrobe.get("items", []) if wardrobe else []

    # ── Build prompt based on whether the wardrobe has items ─────────────────
    if not wardrobe_items:
        prompt = (
            f"A user is thinking of buying: {item_summary}\n\n"
            "They don't have a wardrobe on file yet. Give them 1–2 short, practical "
            "outfit ideas using common clothing pieces that would pair well with this item. "
            "Be specific about silhouettes, shoes, and vibe (e.g. 90s grunge, minimal, Y2K). "
            "Do NOT invent items the user owns. Keep the response under 100 words and "
            "write it as readable plain text, not a list."
        )
    else:
        wardrobe_lines = []
        for w in wardrobe_items:
            name = w.get("name", "unnamed piece")
            w_colors = ", ".join(w.get("colors", []))
            w_tags = ", ".join(w.get("style_tags", []))
            notes = w.get("notes") or ""
            line = f"  - {name}"
            if w_colors:
                line += f" ({w_colors})"
            if w_tags:
                line += f" [{w_tags}]"
            if notes:
                line += f" — {notes}"
            wardrobe_lines.append(line)

        wardrobe_str = "\n".join(wardrobe_lines)

        prompt = (
            f"A user is thinking of buying: {item_summary}\n\n"
            f"Their wardrobe includes:\n{wardrobe_str}\n\n"
            "Suggest 1–2 specific outfits that pair the new item with pieces from their wardrobe. "
            "Use the exact wardrobe item names when you reference them. "
            "Include the overall vibe (e.g. 90s grunge, clean streetwear, soft minimal) and "
            "1–2 concrete styling tips (tucking, layering, shoe choice, etc.). "
            "Keep the response under 120 words and write it as readable plain text, not a list."
        )

    # ── Call LLM ─────────────────────────────────────────────────────────────
    result = _groq_chat(prompt, temperature=0.7)
    if result:
        return result

    # ── Fallback: deterministic string using item fields ─────────────────────
    if wardrobe_items:
        return (
            f"I couldn't generate a personalized outfit this time, but this item should "
            f"work well with neutral bottoms, denim, and casual sneakers. "
            f"Keep the rest of the outfit simple so the {title} stands out."
        )
    else:
        return (
            f"I don't have your wardrobe pieces yet, but the {title} "
            f"({colors_str}, {tags_str}) would pair well with relaxed denim, "
            f"neutral trousers, or classic sneakers. Keep the rest of the look simple "
            f"and let this piece do the talking."
        )


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

def create_fit_card(outfit: str, new_item: dict) -> str:
    """
    Generate a short, shareable outfit caption for the thrifted find.

    Args:
        outfit:   The outfit suggestion string from suggest_outfit().
        new_item: The listing dict for the thrifted item.

    Returns:
        A 2–4 sentence casual OOTD-style caption string. Never raises.
    """
    title = new_item.get("title", "this piece")
    platform = new_item.get("platform", "a resale app")
    price = new_item.get("price", "")
    price_str = f"${price}" if price != "" else "a great price"

    # ── Guard: empty / whitespace outfit ─────────────────────────────────────
    if not outfit or not outfit.strip():
        return (
            f"Found the {title} on {platform} for {price_str} and it's already "
            f"a favourite. Check it out!"
        )

    # ── Build caption prompt ──────────────────────────────────────────────────
    prompt = (
        f"Write a short, casual Instagram/TikTok OOTD caption (2–3 sentences max) for this thrift find:\n\n"
        f"Item: {title}\n"
        f"Platform: {platform}\n"
        f"Price: {price_str}\n"
        f"Outfit idea: {outfit}\n\n"
        "Guidelines:\n"
        "- Sound like a real person posting, not a product description\n"
        "- Mention the item name (or a short version of it) once\n"
        f"- Mention {platform} once\n"
        f"- Mention the price ({price_str}) once\n"
        "- Capture the outfit vibe in specific terms\n"
        "- Feel casual and authentic, maybe add 1 emoji\n"
        "- No hashtags\n"
        "- Output the caption ONLY, no preamble"
    )

    result = _groq_chat(prompt, temperature=0.8)
    if result:
        return result

    # ── Fallback caption ──────────────────────────────────────────────────────
    return (
        f"Scored this {title} on {platform} for {price_str} and honestly "
        f"could not be happier with it. Outfit details below 🖤"
    )
