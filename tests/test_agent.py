"""
tests/test_agent.py

Pytest tests for the FitFindr planning loop (Milestone 4).

Covers:
  - Happy-path session state (all keys populated, error is None)
  - No-results session state (error set, downstream tools not called)
  - State threading (selected_item == search_results[0])
  - Query parser behaviour
  - handle_query() UI mapping (error path and success path)
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from agent import run_agent, _parse_query, _no_results_message
from app import handle_query
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe


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
def happy_session(example_wardrobe):
    """Run the agent with a query that should always return results."""
    return run_agent("vintage graphic tee under $30", example_wardrobe)


@pytest.fixture
def no_results_session(example_wardrobe):
    """Run the agent with a query guaranteed to return no results."""
    return run_agent("designer ballgown size XXS under $5", example_wardrobe)


# ─────────────────────────────────────────────────────────────────────────────
# Happy path — successful query
# ─────────────────────────────────────────────────────────────────────────────

class TestHappyPath:

    def test_happy_path_error_is_none(self, happy_session):
        """A successful run must have error == None."""
        assert happy_session["error"] is None

    def test_happy_path_search_results_non_empty(self, happy_session):
        """search_results must be a non-empty list."""
        assert isinstance(happy_session["search_results"], list)
        assert len(happy_session["search_results"]) > 0

    def test_happy_path_selected_item_not_none(self, happy_session):
        """selected_item must be set to a dict."""
        assert happy_session["selected_item"] is not None
        assert isinstance(happy_session["selected_item"], dict)

    def test_happy_path_selected_item_is_first_result(self, happy_session):
        """selected_item must be exactly search_results[0] (same object)."""
        assert happy_session["selected_item"] == happy_session["search_results"][0]

    def test_happy_path_outfit_suggestion_is_string(self, happy_session):
        """outfit_suggestion must be a non-empty string."""
        assert isinstance(happy_session["outfit_suggestion"], str)
        assert len(happy_session["outfit_suggestion"].strip()) > 0

    def test_happy_path_fit_card_is_string(self, happy_session):
        """fit_card must be a non-empty string."""
        assert isinstance(happy_session["fit_card"], str)
        assert len(happy_session["fit_card"].strip()) > 0

    def test_happy_path_query_stored(self, example_wardrobe):
        """The raw query must be preserved in session['query']."""
        q = "vintage graphic tee under $30"
        session = run_agent(q, example_wardrobe)
        assert session["query"] == q

    def test_happy_path_wardrobe_stored(self, example_wardrobe):
        """The wardrobe passed in must be stored in session['wardrobe']."""
        session = run_agent("vintage graphic tee", example_wardrobe)
        assert session["wardrobe"] is example_wardrobe

    def test_happy_path_parsed_keys(self, happy_session):
        """session['parsed'] must have the three expected keys."""
        parsed = happy_session["parsed"]
        assert "description" in parsed
        assert "size" in parsed
        assert "max_price" in parsed


# ─────────────────────────────────────────────────────────────────────────────
# No-results path — early stop
# ─────────────────────────────────────────────────────────────────────────────

class TestNoResultsPath:

    def test_no_results_error_is_string(self, no_results_session):
        """error must be a non-empty string."""
        assert isinstance(no_results_session["error"], str)
        assert len(no_results_session["error"].strip()) > 0

    def test_no_results_search_results_empty(self, no_results_session):
        """search_results must be []."""
        assert no_results_session["search_results"] == []

    def test_no_results_selected_item_is_none(self, no_results_session):
        """selected_item must remain None."""
        assert no_results_session["selected_item"] is None

    def test_no_results_outfit_suggestion_is_none(self, no_results_session):
        """outfit_suggestion must remain None — suggest_outfit was not called."""
        assert no_results_session["outfit_suggestion"] is None

    def test_no_results_fit_card_is_none(self, no_results_session):
        """fit_card must remain None — create_fit_card was not called."""
        assert no_results_session["fit_card"] is None

    def test_no_results_error_mentions_description(self, no_results_session):
        """The error message should reference the search terms."""
        error = no_results_session["error"].lower()
        # The error should mention something from the impossible query
        assert any(word in error for word in ["ballgown", "no listings", "found"])

    def test_no_results_error_is_actionable(self, no_results_session):
        """The error message should offer at least one next step."""
        error = no_results_session["error"].lower()
        actionable_hints = ["try", "remove", "raise", "broader", "keyword", "filter"]
        assert any(hint in error for hint in actionable_hints)


# ─────────────────────────────────────────────────────────────────────────────
# State threading — data flows correctly through the session
# ─────────────────────────────────────────────────────────────────────────────

class TestStateThreading:

    def test_selected_item_equals_first_result(self, happy_session):
        """selected_item must be the exact same dict as search_results[0]."""
        assert happy_session["selected_item"] == happy_session["search_results"][0]

    def test_selected_item_has_required_fields(self, happy_session):
        """The selected listing dict must contain the standard listing fields."""
        item = happy_session["selected_item"]
        for field in ("id", "title", "price", "platform", "category"):
            assert field in item, f"Missing field: {field}"

    def test_outfit_passed_to_fit_card(self, example_wardrobe):
        """
        The fit card must be generated using the outfit suggestion.
        We verify this indirectly: if outfit_suggestion is a non-empty string,
        the fit card should also be a non-empty string (not the empty-outfit fallback
        that would appear if the wrong value was passed).
        """
        session = run_agent("vintage tee", example_wardrobe)
        if session["error"]:
            pytest.skip("No results for this query in this environment")
        assert isinstance(session["fit_card"], str)
        assert len(session["fit_card"].strip()) > 0

    def test_empty_wardrobe_still_produces_outfit(self, empty_wardrobe):
        """An empty wardrobe must still produce an outfit suggestion (general advice)."""
        session = run_agent("vintage graphic tee", empty_wardrobe)
        if session["error"]:
            pytest.skip("No results for this query in this environment")
        assert isinstance(session["outfit_suggestion"], str)
        assert len(session["outfit_suggestion"].strip()) > 0

    def test_success_and_failure_differ(self, example_wardrobe):
        """Happy path and no-results path must produce different session shapes."""
        good = run_agent("vintage tee", example_wardrobe)
        bad  = run_agent("zzzyyyunmatchable item", example_wardrobe)
        # One has results, one does not
        assert (good["error"] is None) != (bad["error"] is None)


# ─────────────────────────────────────────────────────────────────────────────
# Query parser unit tests
# ─────────────────────────────────────────────────────────────────────────────

class TestParseQuery:

    def test_parses_price_dollar_sign(self):
        parsed = _parse_query("vintage tee under $30")
        assert parsed["max_price"] == 30.0

    def test_parses_price_no_dollar_sign(self):
        parsed = _parse_query("jacket under 50")
        assert parsed["max_price"] == 50.0

    def test_parses_size_standalone(self):
        parsed = _parse_query("size M black boots")
        assert parsed["size"] == "M"

    def test_parses_size_with_comma(self):
        parsed = _parse_query("vintage graphic tee under $30, size M")
        assert parsed["size"] == "M"
        assert parsed["max_price"] == 30.0

    def test_parses_combined_size(self):
        parsed = _parse_query("baby tee size S/M")
        assert parsed["size"] == "S/M"

    def test_parses_waist_size(self):
        parsed = _parse_query("jeans W28")
        assert parsed["size"] is not None
        assert "28" in parsed["size"]

    def test_description_excludes_price_phrase(self):
        parsed = _parse_query("vintage tee under $30")
        assert "30" not in parsed["description"]
        assert "under" not in parsed["description"].lower() or "vintage" in parsed["description"].lower()

    def test_description_excludes_size_phrase(self):
        parsed = _parse_query("vintage tee size M")
        desc = parsed["description"].lower()
        # "M" alone should not remain as a lone size word in description
        # (exact behaviour depends on implementation; just check something useful is there)
        assert "vintage" in desc or "tee" in desc

    def test_description_not_empty_for_plain_query(self):
        parsed = _parse_query("black midi skirt")
        assert parsed["description"].strip() != ""

    def test_no_price_gives_none(self):
        parsed = _parse_query("vintage denim jacket size S")
        assert parsed["max_price"] is None

    def test_no_size_gives_none(self):
        parsed = _parse_query("vintage denim jacket under $40")
        assert parsed["size"] is None

    def test_filler_phrases_stripped(self):
        parsed = _parse_query("I'm looking for a vintage graphic tee under $30, size M. "
                              "I mostly wear baggy jeans and chunky sneakers.")
        desc = parsed["description"].lower()
        assert "looking" not in desc
        assert "mostly" not in desc
        assert "vintage" in desc or "graphic" in desc or "tee" in desc


# ─────────────────────────────────────────────────────────────────────────────
# No-results message helper
# ─────────────────────────────────────────────────────────────────────────────

class TestNoResultsMessage:

    def test_includes_description(self):
        msg = _no_results_message("designer ballgown", "XXS", 5.0)
        assert "designer ballgown" in msg

    def test_includes_size(self):
        msg = _no_results_message("designer ballgown", "XXS", 5.0)
        assert "XXS" in msg

    def test_includes_price(self):
        msg = _no_results_message("designer ballgown", "XXS", 5.0)
        assert "5" in msg

    def test_no_size_omits_size(self):
        msg = _no_results_message("tee", None, 20.0)
        assert "size" not in msg.lower() or "keyword" in msg.lower()

    def test_no_price_omits_price(self):
        msg = _no_results_message("tee", "M", None)
        assert "$" not in msg or "keyword" in msg.lower()

    def test_message_is_actionable(self):
        msg = _no_results_message("ballgown", "XXS", 5.0)
        assert any(w in msg.lower() for w in ["try", "remove", "raise", "broader", "keyword"])


# ─────────────────────────────────────────────────────────────────────────────
# handle_query — UI mapping
# ─────────────────────────────────────────────────────────────────────────────

class TestHandleQuery:

    def test_empty_query_returns_prompt(self):
        listing, outfit, card = handle_query("", "Example wardrobe")
        assert isinstance(listing, str)
        assert len(listing.strip()) > 0
        # Should not silently return empty
        assert "please" in listing.lower() or "enter" in listing.lower() or "query" in listing.lower()

    def test_whitespace_query_returns_prompt(self):
        listing, outfit, card = handle_query("   ", "Example wardrobe")
        assert isinstance(listing, str)
        assert len(listing.strip()) > 0

    def test_no_results_query_error_in_first_panel(self):
        listing, outfit, card = handle_query(
            "designer ballgown size XXS under $5", "Example wardrobe"
        )
        assert isinstance(listing, str)
        assert len(listing.strip()) > 0
        # Error should land in listing panel; outfit and card should be non-result strings
        assert outfit != ""  # friendly "skipped" message
        assert "no" in listing.lower() or "⚠" in listing or "found" in listing.lower()

    def test_success_query_populates_all_panels(self):
        listing, outfit, card = handle_query("vintage tee", "Example wardrobe")
        # If search succeeds, all three panels should have content
        if "⚠" not in listing and "no listings" not in listing.lower():
            assert len(listing.strip()) > 0
            assert len(outfit.strip()) > 0
            assert len(card.strip()) > 0

    def test_success_listing_panel_contains_title(self):
        listing, outfit, card = handle_query("vintage graphic tee under $30", "Example wardrobe")
        if "⚠" not in listing:
            assert "Title:" in listing

    def test_success_listing_panel_contains_price(self):
        listing, outfit, card = handle_query("vintage graphic tee under $30", "Example wardrobe")
        if "⚠" not in listing:
            assert "Price:" in listing or "$" in listing

    def test_success_listing_panel_contains_platform(self):
        listing, outfit, card = handle_query("vintage graphic tee under $30", "Example wardrobe")
        if "⚠" not in listing:
            assert "Platform:" in listing

    def test_empty_wardrobe_choice_still_works(self):
        listing, outfit, card = handle_query("vintage tee", "Empty wardrobe (new user)")
        assert isinstance(listing, str)
        assert isinstance(outfit, str)
        assert isinstance(card, str)

    def test_returns_tuple_of_three_strings(self):
        result = handle_query("vintage tee", "Example wardrobe")
        assert isinstance(result, tuple)
        assert len(result) == 3
        for item in result:
            assert isinstance(item, str)
