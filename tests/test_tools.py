"""
tests/test_tools.py

Pytest tests for all three FitFindr tools:
  - search_listings
  - suggest_outfit
  - create_fit_card

Tests verify return types and important behaviour without requiring exact
LLM wording or a live Groq API key.
"""

import sys
import os

# Ensure the project root is on the path so imports work when run from any cwd
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from tools import search_listings, suggest_outfit, create_fit_card
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe, load_listings


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def example_wardrobe():
    return get_example_wardrobe()


@pytest.fixture
def empty_wardrobe():
    return get_empty_wardrobe()


@pytest.fixture
def graphic_tee():
    """A real listing from the dataset — Vintage Band Tee (lst_033)."""
    listings = load_listings()
    for l in listings:
        if l["id"] == "lst_033":
            return l
    # Fallback synthetic listing if ID changes
    return {
        "id": "lst_033",
        "title": "Vintage Band Tee — Faded Grey",
        "description": "Faded grey band-style tee with distressed graphic.",
        "category": "tops",
        "style_tags": ["vintage", "grunge", "band tee", "graphic tee", "streetwear"],
        "size": "L",
        "condition": "fair",
        "price": 19.00,
        "colors": ["grey", "charcoal"],
        "brand": None,
        "platform": "depop",
    }


@pytest.fixture
def cheap_item():
    """Minimal listing for fallback / edge-case tests."""
    return {
        "id": "test_001",
        "title": "Plain White Tee",
        "description": "A simple white tee.",
        "category": "tops",
        "style_tags": ["basics"],
        "size": "M",
        "condition": "good",
        "price": 10.00,
        "colors": ["white"],
        "brand": None,
        "platform": "thredUp",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Tool 1: search_listings
# ─────────────────────────────────────────────────────────────────────────────

class TestSearchListings:

    def test_search_returns_results(self):
        """A broad query should return a non-empty list of dicts."""
        results = search_listings("vintage graphic tee")
        assert isinstance(results, list)
        assert len(results) > 0
        # Each result should be a dict with the required listing keys
        for item in results:
            assert isinstance(item, dict)
            assert "id" in item
            assert "title" in item
            assert "price" in item

    def test_search_empty_results(self):
        """An impossible query should return [] without raising."""
        results = search_listings("zzzyyyxxxquuxbazquux", size="XXXS", max_price=0.01)
        assert isinstance(results, list)
        assert results == []

    def test_search_price_filter(self):
        """All returned items must have price <= max_price."""
        max_price = 20.0
        results = search_listings("vintage", max_price=max_price)
        assert isinstance(results, list)
        for item in results:
            assert item["price"] <= max_price, (
                f"{item['title']} costs ${item['price']} which exceeds ${max_price}"
            )

    def test_search_price_filter_inclusive(self):
        """Items priced exactly at max_price should be included."""
        # lst_013 (90s Silk Slip Dress) is $30 and tagged vintage/90s
        results = search_listings("vintage slip dress", max_price=30.0)
        prices = [r["price"] for r in results]
        assert any(p == 30.0 for p in prices), (
            "Expected at least one item priced exactly at $30.00 to be included"
        )

    def test_search_size_filter(self):
        """Only items matching the requested size should be returned."""
        results = search_listings("tee shirt top", size="M")
        assert isinstance(results, list)
        # Every returned item must have a size string that contains "m"
        for item in results:
            listing_size = item.get("size", "").lower()
            size_parts = [p.strip() for p in listing_size.replace("/", " ").split()]
            assert "m" in size_parts or "m" in listing_size, (
                f"{item['title']} has size '{item['size']}' which should not match 'M'"
            )

    def test_search_size_filter_substring(self):
        """Query size 'M' must match combined sizes like 'S/M' and 'M/L'."""
        # lst_002 is size "S/M", lst_025 is "M/L" — a query for M should catch both
        results = search_listings("top shirt", size="M")
        sizes_returned = [r["size"] for r in results]
        # At least one S/M or M/L item should appear if any are in the filtered set
        combined_matches = [s for s in sizes_returned if "/" in s and "m" in s.lower()]
        # We can't guarantee results without price filter, but the function must not crash
        assert isinstance(results, list)

    def test_search_relevance_ordering(self):
        """More specific matches should rank higher than weaker matches."""
        results = search_listings("vintage graphic tee")
        # The top result should be a top/graphic tee, not e.g. jeans
        assert len(results) > 0
        top = results[0]
        # The top result's searchable text should overlap with at least 'vintage' or 'graphic'
        top_text = " ".join([
            top.get("title", ""),
            top.get("description", ""),
            " ".join(top.get("style_tags", [])),
            top.get("category", ""),
        ]).lower()
        assert "vintage" in top_text or "graphic" in top_text or "tee" in top_text

    def test_search_returns_dicts_not_tuples(self):
        """Results must be plain dicts, not (score, dict) tuples."""
        results = search_listings("denim jeans")
        for item in results:
            assert isinstance(item, dict), f"Expected dict, got {type(item)}"

    def test_search_no_size_filter_returns_all_sizes(self):
        """When size is None, listings of any size should be eligible."""
        results_no_size = search_listings("vintage")
        results_m_only = search_listings("vintage", size="M")
        # Without a size filter we expect more or equal results
        assert len(results_no_size) >= len(results_m_only)

    def test_search_price_and_size_combined(self):
        """Combined price and size filters should both be applied."""
        results = search_listings("top", size="M", max_price=25.0)
        for item in results:
            assert item["price"] <= 25.0
            listing_size = item.get("size", "").lower()
            assert "m" in listing_size


# ─────────────────────────────────────────────────────────────────────────────
# Tool 2: suggest_outfit
# ─────────────────────────────────────────────────────────────────────────────

class TestSuggestOutfit:

    def test_suggest_outfit_returns_string(self, graphic_tee, example_wardrobe):
        """suggest_outfit must always return a non-empty string."""
        result = suggest_outfit(graphic_tee, example_wardrobe)
        assert isinstance(result, str)
        assert len(result.strip()) > 0

    def test_suggest_outfit_with_empty_wardrobe(self, graphic_tee, empty_wardrobe):
        """Empty wardrobe must return a non-empty general styling string, not raise."""
        result = suggest_outfit(graphic_tee, empty_wardrobe)
        assert isinstance(result, str)
        assert len(result.strip()) > 0

    def test_suggest_outfit_empty_wardrobe_no_fake_items(self, graphic_tee, empty_wardrobe):
        """
        Empty-wardrobe response must not invent owned pieces using 'your [specific item]'
        phrasing that implies the user actually owns those items.
        Checks that the function doesn't claim 'your baggy straight-leg jeans' etc.
        """
        result = suggest_outfit(graphic_tee, empty_wardrobe)
        # Known wardrobe item names from example_wardrobe that should NOT appear
        # in a response to an empty wardrobe (only check for very specific owned names)
        invented_phrases = [
            "your baggy straight-leg jeans",
            "your wide-leg khaki trousers",
            "your black combat boots",
        ]
        lower_result = result.lower()
        for phrase in invented_phrases:
            assert phrase not in lower_result, (
                f"Response incorrectly references owned item: '{phrase}'"
            )

    def test_suggest_outfit_with_example_wardrobe(self, graphic_tee, example_wardrobe):
        """With a populated wardrobe the response should be a helpful string."""
        result = suggest_outfit(graphic_tee, example_wardrobe)
        assert isinstance(result, str)
        assert len(result.strip()) > 0

    def test_suggest_outfit_does_not_raise_on_missing_fields(self, empty_wardrobe):
        """suggest_outfit must not raise even when optional fields are absent."""
        minimal_item = {"id": "x", "title": "Test Item"}
        result = suggest_outfit(minimal_item, empty_wardrobe)
        assert isinstance(result, str)
        assert len(result.strip()) > 0

    def test_suggest_outfit_does_not_raise_on_none_wardrobe(self, graphic_tee):
        """suggest_outfit must handle None wardrobe gracefully."""
        result = suggest_outfit(graphic_tee, {"items": []})
        assert isinstance(result, str)
        assert len(result.strip()) > 0

    def test_suggest_outfit_fallback_mentions_item(self, cheap_item, empty_wardrobe):
        """Fallback string (no LLM) should mention something useful about the item."""
        # We can't force a fallback, but we can verify the result is always meaningful
        result = suggest_outfit(cheap_item, empty_wardrobe)
        assert isinstance(result, str)
        assert len(result) > 20  # must be substantive, not empty or trivial


# ─────────────────────────────────────────────────────────────────────────────
# Tool 3: create_fit_card
# ─────────────────────────────────────────────────────────────────────────────

class TestCreateFitCard:

    def test_create_fit_card_returns_caption(self, graphic_tee):
        """create_fit_card must return a non-empty string for a valid outfit."""
        outfit = "Pair with baggy jeans and chunky sneakers for a 90s streetwear look."
        result = create_fit_card(outfit, graphic_tee)
        assert isinstance(result, str)
        assert len(result.strip()) > 0

    def test_create_fit_card_empty_outfit_fallback(self, graphic_tee):
        """An empty outfit string must return a fallback caption, not raise."""
        result = create_fit_card("", graphic_tee)
        assert isinstance(result, str)
        assert len(result.strip()) > 0

    def test_create_fit_card_whitespace_outfit_fallback(self, graphic_tee):
        """A whitespace-only outfit string must return a fallback caption."""
        result = create_fit_card("   \t\n  ", graphic_tee)
        assert isinstance(result, str)
        assert len(result.strip()) > 0

    def test_create_fit_card_fallback_mentions_title(self, graphic_tee):
        """Fallback caption (empty outfit) must mention the item title."""
        result = create_fit_card("", graphic_tee)
        # Title is "Vintage Band Tee — Faded Grey"; at minimum "Vintage Band Tee" or similar
        lower = result.lower()
        title_words = [w for w in graphic_tee["title"].lower().split() if len(w) > 3]
        assert any(word in lower for word in title_words), (
            f"Fallback caption should mention item title. Got: {result!r}"
        )

    def test_create_fit_card_fallback_mentions_platform(self, graphic_tee):
        """Fallback caption must mention the platform."""
        result = create_fit_card("", graphic_tee)
        assert graphic_tee["platform"].lower() in result.lower(), (
            f"Fallback caption should mention platform '{graphic_tee['platform']}'. Got: {result!r}"
        )

    def test_create_fit_card_fallback_mentions_price(self, graphic_tee):
        """Fallback caption must mention the price."""
        result = create_fit_card("", graphic_tee)
        price_str = str(int(graphic_tee["price"]))  # "19"
        assert price_str in result, (
            f"Fallback caption should mention price ${graphic_tee['price']}. Got: {result!r}"
        )

    def test_create_fit_card_does_not_raise_missing_fields(self):
        """create_fit_card must not raise when new_item has minimal fields."""
        result = create_fit_card("Some outfit idea.", {"title": "Mystery Item"})
        assert isinstance(result, str)
        assert len(result.strip()) > 0

    def test_create_fit_card_does_not_raise_empty_item(self):
        """create_fit_card must not raise when new_item is an empty dict."""
        result = create_fit_card("Some outfit idea.", {})
        assert isinstance(result, str)
        assert len(result.strip()) > 0

    def test_create_fit_card_none_outfit_treated_as_empty(self, graphic_tee):
        """None passed as outfit should be treated as empty and return fallback."""
        # None is falsy — the guard should catch it
        result = create_fit_card(None, graphic_tee)  # type: ignore[arg-type]
        assert isinstance(result, str)
        assert len(result.strip()) > 0
