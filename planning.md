# FitFindr — planning.md

> Complete this document before writing any implementation code.
> Your spec and agent diagram are what you'll use to direct AI tools (Claude, Copilot, ChatGPT, etc.) to generate your implementation — the more specific they are, the more useful the generated code will be.
> Your planning.md will be reviewed as part of your submission.
> Update it before starting any stretch features.

---

## Tools

FitFindr uses three required tools: `search_listings`, `suggest_outfit`, and `create_fit_card`. The agent should always call them in this order unless the search step fails. The tools should use the helper functions in `utils/data_loader.py` instead of manually opening JSON files: `load_listings()` for marketplace listings, `get_example_wardrobe()` for normal styling tests, and `get_empty_wardrobe()` for empty-wardrobe fallback tests.

The listing data contains these fields:
- `id` (str): unique listing ID.
- `title` (str): listing title.
- `description` (str): longer product description.
- `category` (str): item category such as top, shoes, outerwear, etc.
- `style_tags` (list[str]): style/aesthetic tags such as vintage, grunge, streetwear, minimal, etc.
- `size` (str): item size, such as `M`, `S/M`, `W28`, `L`, etc.
- `condition` (str): condition description such as excellent, good, fair, etc.
- `price` (float): item price in dollars.
- `colors` (list[str]): color names.
- `brand` (str | None): brand name if available, otherwise `None`.
- `platform` (str): resale platform, such as Depop, Poshmark, eBay, etc.

The wardrobe data is a dictionary with an `items` key. Each wardrobe item has:
- `id` (str): unique wardrobe item ID.
- `name` (str): user-friendly clothing item name.
- `category` (str): item type such as jeans, sneakers, jacket, etc.
- `colors` (list[str]): item colors.
- `style_tags` (list[str]): tags describing the item style.
- `notes` (str | None): extra user notes about fit, vibe, or use.

### Tool 1: search_listings

**What it does:**
`search_listings` searches the mock secondhand listings database for items matching the user's requested item, optional size, and optional maximum price. It loads listings with `load_listings()`, filters by price and size, scores each remaining listing by keyword overlap with the user's description, drops listings with zero keyword overlap, and returns the matches sorted by best relevance.

The search text for each listing should be built from all useful searchable fields: `title`, `description`, `category`, `style_tags`, `colors`, `brand`, `platform`, and `condition`. `id` should not affect relevance because it is not meaningful user-facing text. Price and size are hard filters, not ranking signals.

**Input parameters:**
- `description` (str): The item description/search phrase extracted from the user query, such as `"vintage graphic tee"`, `"black mini skirt"`, or `"chunky loafers"`.
- `size` (str | None): Optional size filter extracted from the query, such as `"M"`, `"S/M"`, `"W28"`, or `None` if the user did not mention size.
- `max_price` (float | None): Optional price ceiling extracted from the query, such as `30.0`, or `None` if the user did not mention a price limit.

**What it returns:**
A list of listing dictionaries sorted from most relevant to least relevant. Each returned dictionary should preserve the original listing fields:
- `id` (str)
- `title` (str)
- `description` (str)
- `category` (str)
- `style_tags` (list[str])
- `size` (str)
- `condition` (str)
- `price` (float)
- `colors` (list[str])
- `brand` (str | None)
- `platform` (str)

Sorting rule:
1. Higher keyword overlap score first.
2. If two items tie, prefer the lower price.
3. If still tied, keep the original database order for stability.

**Matching details:**
- Normalize text to lowercase.
- Tokenize using alphanumeric words so punctuation does not break matching.
- Ignore very common stopwords from the user query, such as `the`, `a`, `an`, `for`, `under`, `with`, `and`, `size`, and `looking`.
- For size matching, normalize casing and whitespace. A query size of `M` should match exact `M` and combined sizes like `S/M` or `M/L`, but should not accidentally match unrelated text.
- For price matching, include listings where `listing["price"] <= max_price`.

**What happens if it fails or returns nothing:**
If no listings match, return an empty list `[]`. The planning loop must detect the empty list, set `session["error"]` to an actionable message, and stop immediately. It must not call `suggest_outfit` or `create_fit_card` with empty input.

Example error message:
`"No listings found for 'vintage graphic tee' in size M under $30. Try removing the size filter, raising the price limit, or searching broader words like 'graphic tee' or 'band tee'."`

---

### Tool 2: suggest_outfit

**What it does:**
`suggest_outfit` creates a styling recommendation that pairs the selected secondhand item with the user's wardrobe. It should use the selected listing from `search_listings` as `new_item` and the wardrobe dictionary as `wardrobe`. If the wardrobe has items, the suggestion should mention 1–3 specific wardrobe pieces by name and explain why they match. If the wardrobe is empty, the tool should give general styling advice without pretending the user owns items.

**Input parameters:**
- `new_item` (dict): The selected listing dictionary. It must include at least `title`, `category`, `style_tags`, `colors`, `price`, and `platform`.
- `wardrobe` (dict): The user's wardrobe dictionary with an `items` list. Each item in `wardrobe["items"]` should include `id`, `name`, `category`, `colors`, `style_tags`, and `notes`.

**What it returns:**
A string with a practical outfit idea. A good response should include:
- The selected item's title or clear item description.
- Specific wardrobe item names when the wardrobe is not empty.
- A short style/vibe explanation, such as `90s grunge`, `clean streetwear`, `soft minimal`, or `Y2K casual`.
- 1–2 concrete styling tips, such as how to layer, tuck, cuff, accessorize, or choose shoes.

Example return when wardrobe has items:
`"Pair the Vintage Band Tee — Faded Grey with your baggy straight-leg jeans and chunky white sneakers for an easy 90s streetwear look. Add your black crossbody bag to balance the faded graphic, and half-tuck the tee so the outfit still has shape."`

Example return when wardrobe is empty:
`"I do not have wardrobe pieces to match from yet, but this faded band tee would style well with relaxed denim, black cargos, or a worn-in leather jacket. Keep the shoes chunky and casual, then half-tuck the tee or roll the sleeves once for shape."`

**What happens if it fails or returns nothing:**
If `wardrobe["items"]` is empty, return general styling advice instead of failing. If the LLM or styling call fails, return a deterministic fallback string based on the listing's tags and colors:
`"I couldn't generate a personalized outfit this time, but this item should work well with neutral bottoms, denim, and casual sneakers. Keep the rest of the outfit simple so the item stands out."`

---

### Tool 3: create_fit_card

**What it does:**
`create_fit_card` turns the outfit suggestion and selected listing into a short social-media-style fit card/caption. The caption should feel casual and authentic, like an OOTD post, and should naturally include the item's title, price, platform, and outfit vibe.

**Input parameters:**
- `outfit` (str): The outfit suggestion returned by `suggest_outfit`.
- `new_item` (dict): The selected listing dictionary from `search_listings`.

**What it returns:**
A 1–3 sentence string suitable for Instagram, TikTok, or a style card. It should:
- Mention the item title or simplified item name.
- Mention the platform exactly once.
- Mention the price exactly once.
- Sound casual, not like a product ad.
- Avoid inventing details not present in the listing or outfit suggestion.

Example return:
`"thrifted this vintage band tee off depop for $19 and it fits perfectly with my baggy jeans + chunky sneakers 🖤 easy 90s grunge look without trying too hard"`

**What happens if it fails or returns nothing:**
If `outfit` is missing, empty, or whitespace-only, build a safe fallback caption from the listing fields:
`"found this {title} on {platform} for ${price} — easy piece to style with denim, sneakers, and simple layers 🖤"`

---

## Planning Loop

**How does your agent decide which tool to call next?**

The planning loop is a sequential pipeline inside `run_agent(query, wardrobe)`. The order is fixed: parse user query → search listings → stop on empty results or select top listing → suggest outfit → create fit card → return session.

Detailed conditional logic:

1. Start `run_agent(query, wardrobe)`.
2. Create a new session dictionary with these default values:
   - `query`: the raw user query.
   - `wardrobe`: the wardrobe dictionary passed into the function.
   - `parsed`: `None`.
   - `search_results`: `[]`.
   - `selected_item`: `None`.
   - `outfit_suggestion`: `None`.
   - `fit_card`: `None`.
   - `error`: `None`.
3. Parse the user query into search filters:
   - `description`: the clothing item/search phrase.
   - `size`: a string if the user mentions a size, otherwise `None`.
   - `max_price`: a float if the user mentions a price limit, otherwise `None`.
4. Save those filters in `session["parsed"]`.
5. Call `search_listings(description, size, max_price)`.
6. Save the returned list in `session["search_results"]`.
7. Check `session["search_results"]`:
   - If it is empty, set `session["error"]` to a specific user-facing message explaining the failed filters and offering a next step. Then return the session immediately.
   - If it is not empty, set `session["selected_item"] = session["search_results"][0]`.
8. Call `suggest_outfit(session["selected_item"], session["wardrobe"])`.
9. Save the result in `session["outfit_suggestion"]`.
10. Call `create_fit_card(session["outfit_suggestion"], session["selected_item"])`.
11. Save the result in `session["fit_card"]`.
12. Return the completed session.

Important rule: `suggest_outfit` and `create_fit_card` should never be called when `search_results` is empty, because there is no `selected_item` to style or caption.

---

## State Management

**How does information from one tool get passed to the next?**

FitFindr passes information through one shared session dictionary. Each stage reads from and writes to this dictionary so that the final app/UI can show the search result, outfit idea, fit card, or error message.

Session keys:

| Key | Type | Set by | Used by | Meaning |
|---|---|---|---|---|
| `query` | str | `_new_session` / `run_agent` | parser and UI | Raw user request. |
| `wardrobe` | dict | `_new_session` / `run_agent` | `suggest_outfit` | User wardrobe from `get_example_wardrobe()` or `get_empty_wardrobe()`. |
| `parsed` | dict | query parser | `search_listings` | Extracted filters: `description`, `size`, `max_price`. |
| `search_results` | list[dict] | `search_listings` | planning loop and UI | Ranked matching listings. |
| `selected_item` | dict | None | planning loop | `suggest_outfit`, `create_fit_card`, UI | Top listing selected as the recommended buy. |
| `outfit_suggestion` | str | None | `suggest_outfit` | `create_fit_card`, UI | Styling recommendation. |
| `fit_card` | str | None | `create_fit_card` | UI | Final social caption / fit card copy. |
| `error` | str | None | planning loop or fallback handlers | UI | User-facing error message when the flow stops early. |

Testing wardrobe helpers:
- Use `get_example_wardrobe()` for the happy path because it provides real wardrobe items that `suggest_outfit` can reference.
- Use `get_empty_wardrobe()` to test the fallback path where the agent gives general styling advice instead of referencing owned items.

---

## Error Handling

For each tool, describe the specific failure mode you're handling and what the agent does in response.

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| `search_listings` | No listings match the description, size, and/or price filters. | Set `session["error"]` to a specific message such as: `"No listings found for 'vintage graphic tee' in size M under $30. Try removing the size filter, raising the price limit, or searching broader words like 'graphic tee' or 'band tee'."` Return the session immediately. Do not call `suggest_outfit` or `create_fit_card`. |
| `search_listings` | Bad or missing parsed description. | Use a safe fallback description from the raw query. If the description is still empty, set `session["error"]` to: `"I need an item description to search. Try something like 'vintage graphic tee under $30' or 'black loafers size 8'."` Then return early. |
| `suggest_outfit` | Wardrobe is empty. | Return general styling advice for the selected item without naming wardrobe pieces. The message should suggest common pairings, colors, shoes, and styling tips. |
| `suggest_outfit` | LLM/styling generation fails. | Return deterministic fallback advice: `"I couldn't generate a personalized outfit this time, but this item should work well with neutral bottoms, denim, and casual sneakers. Keep the rest of the outfit simple so the item stands out."` |
| `create_fit_card` | Outfit input is missing, empty, or whitespace-only. | Return a fallback caption using only listing details: `"found this {title} on {platform} for ${price} — easy piece to style with denim, sneakers, and simple layers 🖤"` |
| `create_fit_card` | Listing is missing optional fields such as brand. | Do not crash and do not print `None` awkwardly. Omit missing optional fields from the caption. |

---

## Architecture

```mermaid
flowchart TD
    U[User query + wardrobe choice] --> P[Planning Loop: run_agent]

    P --> S0[Session State initialized]
    S0 --> Parse[Parse query into description, size, max_price]
    Parse --> SaveParsed[session.parsed = filters]

    SaveParsed --> Search[Tool 1: search_listings description, size, max_price]
    Search --> SaveResults[session.search_results = ranked listings]
    SaveResults --> Found{Any listings found?}

    Found -- No --> Err[session.error = actionable no-results message]
    Err --> Stop[Return session early]

    Found -- Yes --> Select[session.selected_item = search_results[0]]
    Select --> Outfit[Tool 2: suggest_outfit selected_item + wardrobe]
    Outfit --> SaveOutfit[session.outfit_suggestion = styling text]

    SaveOutfit --> Card[Tool 3: create_fit_card outfit_suggestion + selected_item]
    Card --> SaveCard[session.fit_card = caption]
    SaveCard --> Done[Return completed session]

    S0 -. shared state stores all outputs .-> SaveParsed
    SaveParsed -. shared state .-> SaveResults
    SaveResults -. shared state .-> Select
    Select -. shared state .-> SaveOutfit
    SaveOutfit -. shared state .-> SaveCard
```

Text version of the same flow:

```text
User query + wardrobe
    │
    ▼
run_agent(query, wardrobe)
    │
    ├─ create session state
    │
    ├─ parse query
    │     └─ session["parsed"] = {description, size, max_price}
    │
    ├─ search_listings(description, size, max_price)
    │     ├─ returns []
    │     │     └─ session["error"] = actionable no-results message
    │     │        return session early
    │     │
    │     └─ returns [listing_1, listing_2, ...]
    │           └─ session["selected_item"] = listing_1
    │
    ├─ suggest_outfit(selected_item, wardrobe)
    │     ├─ wardrobe has items -> mention specific wardrobe pieces
    │     └─ wardrobe empty -> general styling advice
    │
    ├─ create_fit_card(outfit_suggestion, selected_item)
    │
    └─ return session with selected_item, outfit_suggestion, and fit_card
```

---

## AI Tool Plan

The AI tool will be used as an implementation assistant, not as a replacement for the spec. I will only use generated code after checking it against this planning document and running tests.

### Milestone 2 — Planning/spec completion
- **AI Tool:** ChatGPT.
- **Input:** The assignment instructions, the current `planning.md`, and the required sections: Tools, Planning Loop, State Management, Error Handling, Architecture, AI Tool Plan, and A Complete Interaction.
- **Expected production:** A clearer, implementation-ready `planning.md` with exact tool inputs, return values, failure handling, state keys, and a text-based architecture diagram.
- **Verification plan:** Check that every required section is filled in, the diagram is text-based, the complete interaction traces all three tools, and the no-results path stops before calling `suggest_outfit`.

### Milestone 3 — Implement `search_listings`
- **AI Tool:** Claude, Copilot, ChatGPT, or Antigravity.
- **Input:** The `Tool 1: search_listings` section, the listing field notes from the Tools section, and `utils/data_loader.py` showing `load_listings()`.
- **Expected production:** A `search_listings(description, size=None, max_price=None)` function in `tools.py` that loads listings with `load_listings()`, filters by price and size, computes keyword overlap using listing text fields, drops zero-overlap listings, and returns sorted listing dictionaries.
- **Verification plan:** Before running the code, inspect that it uses `load_listings()` and does not manually rewrite file-loading logic. Then run tests for: a normal query, a size filter, a max-price filter, a query with no results, and sorting/tie-breaking by lower price.

### Milestone 3 — Implement `suggest_outfit`
- **AI Tool:** Claude, Copilot, ChatGPT, or Antigravity.
- **Input:** The `Tool 2: suggest_outfit` section, the wardrobe schema notes, and examples from `get_example_wardrobe()` and `get_empty_wardrobe()`.
- **Expected production:** A `suggest_outfit(new_item, wardrobe)` function that references specific wardrobe items when available and returns general styling advice when `wardrobe["items"]` is empty.
- **Verification plan:** Test with `get_example_wardrobe()` and confirm the output mentions at least one real wardrobe item name. Test with `get_empty_wardrobe()` and confirm it does not invent owned items.

### Milestone 3 — Implement `create_fit_card`
- **AI Tool:** Claude, Copilot, ChatGPT, or Antigravity.
- **Input:** The `Tool 3: create_fit_card` section and the desired caption examples.
- **Expected production:** A `create_fit_card(outfit, new_item)` function that returns a casual 1–3 sentence caption mentioning item title/name, platform, and price exactly once.
- **Verification plan:** Test that the caption includes the platform and price, does not crash when `outfit` is empty, and uses the fallback caption when needed.

### Milestone 4 — Implement planning loop and app wiring
- **AI Tool:** Claude, Copilot, ChatGPT, or Antigravity.
- **Input:** The Planning Loop, State Management, Error Handling, and Architecture sections.
- **Expected production:** A `run_agent(query, wardrobe)` function in `agent.py` that manages session state, parses filters, calls tools in the correct order, stops early on empty search results, and returns the final session. Also an app handler that displays either the three success outputs or the error message.
- **Verification plan:** Run one happy-path query and confirm all three tools are called in order. Run one impossible query and confirm only `search_listings` runs, `session["error"]` is set, and `selected_item`, `outfit_suggestion`, and `fit_card` remain empty/`None`.

### Final testing before submission
- **AI Tool:** ChatGPT or Copilot for help writing tests only.
- **Input:** The Error Handling table, complete interaction walkthrough, and actual tool implementations.
- **Expected production:** A small test script or checklist covering the happy path, no-results path, empty-wardrobe path, and missing-outfit fallback.
- **Verification plan:** Run tests manually, compare outputs to the spec, and revise implementation if the behavior differs from `planning.md`.

---

## A Complete Interaction (Step by Step)

FitFindr is a secondhand shopping and styling assistant. It searches resale listings based on the user's item description, size, and price limit; if a match is found, it styles the top listing using the user's wardrobe and creates a short fit-card caption. If the search returns no listings, FitFindr gives the user a specific suggestion for changing the search and stops instead of calling the outfit or caption tools with empty input.

**Example user query:**
`"I'm looking for a vintage graphic tee under $30, size M. I mostly wear baggy jeans and chunky sneakers."`

### Step 0 — Parse the user query
- **Parsed description:** `"vintage graphic tee"`
- **Parsed size:** `"M"`
- **Parsed max_price:** `30.0`
- **Saved state:** `session["parsed"] = {"description": "vintage graphic tee", "size": "M", "max_price": 30.0}`

### Step 1 — Search listings
- **Tool called:** `search_listings(description="vintage graphic tee", size="M", max_price=30.0)`
- **Why this tool is called first:** The agent needs to find a real secondhand listing before it can suggest an outfit or create a fit card.
- **What it returns:** A ranked list of matching listing dictionaries. For example, it may return:
  1. `Faded Band Tee` — `$22`, `Depop`, `Good condition`, size `M`
  2. another graphic tee match
  3. another vintage tee match
- **State update:** `session["search_results"] = results`
- **Branch check:** Because `results` is not empty, the agent continues.
- **Selected item:** `session["selected_item"] = results[0]`, which is `Faded Band Tee — $22, Depop, Good condition`.

### Step 2 — Suggest outfit
- **Tool called:** `suggest_outfit(new_item=session["selected_item"], wardrobe=session["wardrobe"])`
- **Why this tool is called second:** The agent now has a selected item and can style it with the user's wardrobe.
- **Input:**
  - `new_item`: the selected `Faded Band Tee` listing dictionary.
  - `wardrobe`: example wardrobe containing pieces like wide-leg/baggy jeans and chunky shoes.
- **What it returns:**
  `"Pair this with your wide-leg jeans and platform Docs for a classic 90s grunge look. Roll the sleeves once and tuck the front corner slightly for shape."`
- **State update:** `session["outfit_suggestion"] = outfit text`

### Step 3 — Create fit card
- **Tool called:** `create_fit_card(outfit=session["outfit_suggestion"], new_item=session["selected_item"])`
- **Why this tool is called third:** The agent has both the selected listing and styling suggestion, so it can turn the result into a shareable caption.
- **What it returns:**
  `"thrifted this faded band tee off depop for $22 and honestly it was made for my wide-legs 🖤 full look in my stories"`
- **State update:** `session["fit_card"] = fit card text`

### Final success output to the user
The app should show three clear outputs:

**Top listing found**
```text
Title: Faded Band Tee
Price: $22.00
Platform: Depop
Condition: Good condition
Size: M
```

**Outfit idea**
```text
Pair this with your wide-leg jeans and platform Docs for a classic 90s grunge look. Roll the sleeves once and tuck the front corner slightly for shape.
```

**Fit card**
```text
thrifted this faded band tee off depop for $22 and honestly it was made for my wide-legs 🖤 full look in my stories
```

### Error path walkthrough

**Example failing query:**
`"I'm looking for a vintage graphic tee under $5, size XXS."`

1. The parser extracts `description="vintage graphic tee"`, `size="XXS"`, and `max_price=5.0`.
2. The agent calls `search_listings(description="vintage graphic tee", size="XXS", max_price=5.0)`.
3. `search_listings` returns `[]`.
4. The planning loop sets:
   `session["error"] = "No listings found for 'vintage graphic tee' in size XXS under $5. Try removing the size filter, raising the price limit, or searching broader words like 'graphic tee' or 'band tee'."`
5. The agent returns immediately.
6. The agent does **not** call `suggest_outfit`.
7. The agent does **not** call `create_fit_card`.

**Final error output to the user:**
```text
No listings found for 'vintage graphic tee' in size XXS under $5. Try removing the size filter, raising the price limit, or searching broader words like 'graphic tee' or 'band tee'.
```
