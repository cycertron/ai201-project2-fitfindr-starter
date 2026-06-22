# FitFindr

FitFindr is a secondhand fashion assistant that helps a user find an item from a mock resale listing database, style it with their existing wardrobe, and generate a short social media fit card. The project is built as a small agent system: the agent parses the user's request, searches listings, selects the best match, suggests an outfit, and creates a caption-like fit card.

The main goal of this project was not only to make the app work, but to practice agent design discipline: writing a spec first, testing each tool in isolation, wiring state through a planning loop, and deliberately testing failure modes.

---

## Tool Inventory

### 1. `search_listings(description, size=None, max_price=None)`

**Inputs:**

* `description` (`str`): A text description of what the user is looking for, such as `"vintage graphic tee"`.
* `size` (`str | None`): Optional size filter, such as `"M"`, `"S/M"`, or `"XXS"`.
* `max_price` (`float | int | None`): Optional maximum price filter.

**Output:**

* Returns a `list[dict]`.
* Each dictionary is one matching listing from `data/listings.json`.
* Each listing contains fields such as:

  * `id`
  * `title`
  * `description`
  * `category`
  * `style_tags`
  * `size`
  * `condition`
  * `price`
  * `colors`
  * `brand`
  * `platform`

**Purpose:**

This tool searches the mock secondhand listing database. It filters listings by price and size, scores listings based on keyword overlap with the user's description, and returns the most relevant matches sorted by relevance.

**Failure behavior:**

If no listings match, it returns an empty list `[]` instead of raising an exception.

Example failure test:

```bash
python -c "from tools import search_listings; print(search_listings('designer ballgown', size='XXS', max_price=5))"
```

Observed output:

```python
[]
```

---

### 2. `suggest_outfit(new_item, wardrobe)`

**Inputs:**

* `new_item` (`dict`): The selected listing dictionary returned from `search_listings`.
* `wardrobe` (`dict`): A wardrobe object containing an `"items"` list. Each wardrobe item includes fields such as `id`, `name`, `category`, `colors`, `style_tags`, and `notes`.

**Output:**

* Returns a `str`.
* The string contains an outfit suggestion that pairs the new item with the user's wardrobe pieces when possible.

**Purpose:**

This tool uses the selected secondhand item and the user's wardrobe to suggest how to style the item. If the wardrobe has items, the suggestion references specific wardrobe pieces. If the wardrobe is empty, the tool gives general styling advice instead.

**Failure behavior:**

If `wardrobe["items"]` is empty, the tool does not crash. It returns a useful general styling suggestion.

Example failure test:

```bash
python -c "
from tools import search_listings, suggest_outfit
from utils.data_loader import get_empty_wardrobe
results = search_listings('vintage graphic tee', size=None, max_price=50)
print(suggest_outfit(results[0], get_empty_wardrobe()))
"
```

Observed behavior:

The tool returned a useful general styling string instead of raising an exception.

---

### 3. `create_fit_card(outfit, new_item)`

**Inputs:**

* `outfit` (`str`): The outfit suggestion returned from `suggest_outfit`.
* `new_item` (`dict`): The selected listing dictionary from `search_listings`.

**Output:**

* Returns a `str`.
* The string is a short, casual social media-style fit card or caption.

**Purpose:**

This tool turns the outfit suggestion and selected listing into a short caption that could be used for an Instagram story, TikTok post, or outfit card. It includes details like the item, platform, price, and styling vibe.

**Failure behavior:**

If the `outfit` string is empty or missing, the tool returns a fallback caption using the listing title, platform, and price instead of crashing.

Example failure test:

```bash
python -c "
from tools import search_listings, create_fit_card
results = search_listings('vintage graphic tee', size=None, max_price=50)
print(create_fit_card('', results[0]))
"
```

Observed output:

```text
Found the Y2K Baby Tee — Butterfly Print on depop for $18.0 and it's already a favourite. Check it out!
```

---

## Planning Loop

The planning loop is implemented in `run_agent()` inside `agent.py`.

The agent follows a conditional sequence:

1. Start with the user's raw query and wardrobe.
2. Initialize a `session` dictionary to store all intermediate and final state.
3. Parse the query into structured search fields:

   * `description`
   * `size`
   * `max_price`
4. Store the parsed result in `session["parsed"]`.
5. Call `search_listings(description, size, max_price)`.
6. Store the returned list in `session["search_results"]`.
7. Check whether any listings were found.

If `search_listings` returns an empty list:

1. Set `session["error"]` to a helpful no-results message.
2. Keep `session["selected_item"]` as `None`.
3. Keep `session["outfit_suggestion"]` as `None`.
4. Keep `session["fit_card"]` as `None`.
5. Return the session immediately.
6. Do not call `suggest_outfit`.
7. Do not call `create_fit_card`.

If `search_listings` returns one or more listings:

1. Select the first result with `search_results[0]`.
2. Store it in `session["selected_item"]`.
3. Pass that exact selected listing into `suggest_outfit`.
4. Store the returned outfit string in `session["outfit_suggestion"]`.
5. Pass the outfit suggestion and selected listing into `create_fit_card`.
6. Store the returned caption in `session["fit_card"]`.
7. Return the completed session.

This means the agent does not blindly call every tool every time. Its behavior changes depending on whether the search step succeeds or fails.

---

## State Management

FitFindr uses a shared `session` dictionary to pass data between steps. This keeps the planning loop easier to debug because every important value is stored in one place.

The session stores:

* `query`: The original user query.
* `parsed`: The structured search parameters extracted from the query.
* `search_results`: The list returned by `search_listings`.
* `selected_item`: The top listing selected from the search results.
* `wardrobe`: The wardrobe dictionary passed into the agent.
* `outfit_suggestion`: The string returned by `suggest_outfit`.
* `fit_card`: The string returned by `create_fit_card`.
* `error`: A string error message if the agent stops early.

State flows through the tools like this:

```text
user query
  ↓
parsed search fields
  ↓
search_listings(...)
  ↓
search_results
  ↓
selected_item
  ↓
suggest_outfit(selected_item, wardrobe)
  ↓
outfit_suggestion
  ↓
create_fit_card(outfit_suggestion, selected_item)
  ↓
fit_card
```

The no-results branch stops after `search_listings`, which prevents later tools from receiving empty or invalid input.

---

## Error Handling Strategy

### `search_listings`

**Failure mode:**

No listings match the user's description, size, or price filter.

**Agent response:**

The tool returns `[]`. The planning loop checks for the empty list, sets `session["error"]`, and returns early.

Concrete test:

```bash
python -c "from tools import search_listings; print(search_listings('designer ballgown', size='XXS', max_price=5))"
```

Result:

```python
[]
```

Full-agent behavior:

When the full agent receives an impossible query, it returns a session where:

* `search_results` is `[]`
* `selected_item` is `None`
* `outfit_suggestion` is `None`
* `fit_card` is `None`
* `error` contains a helpful message explaining what failed and what the user can try next

Example message:

```text
No listings found for "designer ballgown" with size XXS under $5. Try removing the size filter, raising your budget, or using broader keywords.
```

---

### `suggest_outfit`

**Failure mode:**

The wardrobe is empty.

**Agent response:**

The tool still returns general styling advice based on the selected listing's category, colors, and style tags. It does not reference specific wardrobe items when no wardrobe items exist.

Concrete test:

```bash
python -c "
from tools import search_listings, suggest_outfit
from utils.data_loader import get_empty_wardrobe
results = search_listings('vintage graphic tee', size=None, max_price=50)
print(suggest_outfit(results[0], get_empty_wardrobe()))
"
```

Observed behavior:

The function returned a useful styling suggestion instead of crashing.

---

### `create_fit_card`

**Failure mode:**

The outfit suggestion is empty.

**Agent response:**

The tool returns a fallback fit-card caption using the selected listing's title, platform, and price.

Concrete test:

```bash
python -c "
from tools import search_listings, create_fit_card
results = search_listings('vintage graphic tee', size=None, max_price=50)
print(create_fit_card('', results[0]))
"
```

Observed output:

```text
Found the Y2K Baby Tee — Butterfly Print on depop for $18.0 and it's already a favourite. Check it out!
```

---

## Spec Reflection

One way the spec helped me was by making the planning loop much easier to implement. Because I had already written down the exact order of tool calls and the early-return error branch, I knew that the agent should stop immediately when `search_listings` returned an empty list. That prevented me from accidentally calling `suggest_outfit` or `create_fit_card` with invalid input.

One way the implementation diverged from the original spec was in query parsing. The original plan described parsing the user's query into `description`, `size`, and `max_price`, but during testing I noticed that command-line shell behavior could remove `$5` when the command was wrapped in double quotes. I adjusted my testing approach by using single quotes around the full `python -c` command and kept the parser simple and debuggable instead of making the whole planning loop depend on another LLM call.

Another small divergence was that I made the LLM-powered tools return fallback strings when Groq is unavailable. This was important because tests should still verify the agent's logic even if the API key is missing or the network is unavailable.

---

## AI Usage

I used Claude Code as an implementation assistant, but I did not ask it to build the whole project at once. I gave it one milestone at a time and used my `planning.md` as the directed by the assignment guidelines.

I had a problem in using claude code in the 
### Instance 1: Tool implementation

I directed Claude Code to implement each tool in `tools.py` one at a time. For `search_listings`, I gave it the tool spec from `planning.md` and told it to use `load_listings()` instead of rewriting file-loading logic. I specifically checked that the function returned a list of listing dictionaries, not score tuples, and that the no-results case returned `[]` instead of raising an exception. I revised the output expectations because AI-generated code can sometimes overcomplicate search ranking. I kept the behavior simple: filter by price and size, score by keyword overlap, drop zero-overlap listings, and sort the remaining results.

I also used ChatGPT in the further polishing of my written documents to correct my grammar and make the document look more concise with proper formats.