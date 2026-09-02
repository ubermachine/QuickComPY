"""Tests for the shared scraping helpers in backend_py/scrapers/common.py.

Pure functions only -- no browser, no network.
"""

import asyncio
import json
import os
import sys

_project_root = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import pytest

from backend_py.scrapers import common


# ---------------------------------------------------------------------------
# Price derivation
# ---------------------------------------------------------------------------

def test_price_fields_with_discount():
    price, orig, savings, discount = common.price_fields(180, 240)
    assert price == "₹180"
    assert orig == "₹240"
    assert savings == "₹60"
    assert discount == "25% OFF"


def test_price_fields_without_discount():
    """MRP equal to selling price is not a discount."""
    price, orig, savings, discount = common.price_fields(36, 36)
    assert price == "₹36"
    assert (orig, savings, discount) == (None, None, None)


def test_price_fields_ignores_mrp_below_selling_price():
    """Stale MRP data must not produce a negative saving."""
    price, orig, savings, discount = common.price_fields(100, 80)
    assert price == "₹100"
    assert (orig, savings, discount) == (None, None, None)


def test_price_fields_parses_prefixed_strings():
    price, orig, _, _ = common.price_fields("₹115", "₹220")
    assert price == "₹115"
    assert orig == "₹220"


def test_price_fields_missing_price():
    assert common.price_fields(None, None)[0] == "N/A"


def test_money_keeps_paise_when_present():
    assert common.money(36.5) == "₹36.50"
    assert common.money(36.0) == "₹36"


# ---------------------------------------------------------------------------
# Relevance ranking
# ---------------------------------------------------------------------------

def _names(products):
    return [p["name"] for p in products]


def test_ranking_demotes_sponsored_filler():
    """Blinkit leads a "milk" search with an unrelated sponsored card."""
    products = [
        {"name": "Let's Try Fruit Cake Rusk with Goodness of Wheat"},
        {"name": "Amul Gold Full Cream Milk"},
    ]
    assert _names(common.rank_by_relevance(products, "milk"))[0] == "Amul Gold Full Cream Milk"


def test_ranking_prefers_the_actual_product_over_an_ingredient_mention():
    """"Cocoa Butter" in a lotion title should not outrank real butter."""
    products = [
        {"name": "Plum Vanilla Caramello Body Lotion | Cocoa Butter & Vitamin B5"},
        {"name": "Amul Unsalted Butter"},
    ]
    assert _names(common.rank_by_relevance(products, "butter"))[0] == "Amul Unsalted Butter"


def test_ranking_is_stable_within_a_score_band():
    """Equally good matches keep the platform's own ordering."""
    products = [
        {"name": "Amul Taaza Toned Milk"},
        {"name": "Amul Gold Toned Milk"},
    ]
    assert _names(common.rank_by_relevance(products, "milk")) == [
        "Amul Taaza Toned Milk",
        "Amul Gold Toned Milk",
    ]


def test_ranking_leaves_synonym_results_untouched():
    """No lexical overlap means the platform matched semantically; trust it."""
    products = [{"name": "Amul Masti Dahi"}, {"name": "Nestle A+ Dahi"}]
    assert _names(common.rank_by_relevance(products, "curd")) == [
        "Amul Masti Dahi",
        "Nestle A+ Dahi",
    ]


def test_ranking_never_drops_products():
    products = [{"name": f"Item {i}"} for i in range(5)]
    assert len(common.rank_by_relevance(products, "milk")) == 5


def test_relevance_score_zero_for_no_overlap():
    assert common.relevance_score("Amul Masti Dahi", "shampoo") == 0.0


def test_whole_word_beats_substring():
    """"milk" as its own word should outrank "milkshake"."""
    whole = common.relevance_score("Amul Toned Milk", "milk")
    substring = common.relevance_score("Amul Toned Milkshake", "milk")
    assert whole > substring


# ---------------------------------------------------------------------------
# Dedupe and cleaning
# ---------------------------------------------------------------------------

def test_dedupe_keeps_first_occurrence():
    products = [
        {"id": "a", "name": "First"},
        {"id": "a", "name": "Duplicate"},
        {"id": "b", "name": "Second"},
    ]
    assert _names(common.dedupe(products)) == ["First", "Second"]


def test_dedupe_falls_back_to_name_when_id_missing():
    products = [{"name": "Amul Butter"}, {"name": "Amul Butter"}]
    assert len(common.dedupe(products)) == 1


def test_clean_collapses_whitespace_and_empties():
    assert common.clean("  Amul   Butter \n") == "Amul Butter"
    assert common.clean("") is None
    assert common.clean("   ") is None
    assert common.clean(None) is None


# ---------------------------------------------------------------------------
# ScrapeResult
# ---------------------------------------------------------------------------

def test_scrape_result_serialises_for_the_api():
    r = common.ScrapeResult([{"name": "x"}], common.BLOCKED, "nope")
    assert r.to_dict() == {
        "products": [{"name": "x"}],
        "status": "blocked",
        "message": "nope",
    }


def test_scrape_result_defaults_to_empty_ok():
    r = common.ScrapeResult()
    assert r.products == [] and r.status == common.OK


@pytest.mark.parametrize("status", [common.OK, common.EMPTY, common.BLOCKED,
                                    common.TIMEOUT, common.ERROR])
def test_statuses_are_distinct_strings(status):
    assert isinstance(status, str) and status


# ---------------------------------------------------------------------------
# Block detection
#
# Regression guard for a real bug: the first version scanned raw HTML for the
# substring "awswaf", which matches the AWS WAF SDK script tag Swiggy embeds on
# every healthy page (edge.sdk.awswaf.com/challenge.js). Every Instamart page
# therefore looked blocked, and because BLOCKED is the one status run_search
# will not retry, a transient miss became a permanent failure.
# ---------------------------------------------------------------------------

class _FakePage:
    """Stands in for a zendriver page, returning a canned block probe."""

    def __init__(self, *, widget=None, title="", text="", length=None):
        self._payload = {
            "widget": widget,
            "title": title,
            "text": text,
            "length": length if length is not None else len(text),
        }
        self.evaluated = 0

    async def evaluate(self, _expression):
        self.evaluated += 1
        return json.dumps(self._payload)


def _run(coro):
    return asyncio.run(coro)


def test_healthy_swiggy_page_is_not_blocked():
    """The WAF SDK loading is not a block. This is the exact false positive."""
    page = _FakePage(
        title="Buy Milk Online - Swiggy Instamart",
        text="Amul Gold Full Cream Milk " * 400,  # a real app shell, ~10k chars
    )
    assert _run(common._page_looks_blocked(page)) is False


def test_visible_challenge_widget_is_blocked():
    page = _FakePage(widget="#captchacharacters", title="Amazon.in", text="short")
    assert _run(common._page_looks_blocked(page)) is True


def test_small_page_with_challenge_phrase_is_blocked():
    page = _FakePage(title="Access Denied", text="Access denied. Request blocked.")
    assert _run(common._page_looks_blocked(page)) is True


def test_challenge_phrase_inside_a_full_page_is_not_blocked():
    """A big page merely mentioning the phrase is a catalogue, not a challenge."""
    page = _FakePage(
        title="Search results",
        text="unusual traffic " + ("product listing " * 500),
    )
    assert _run(common._page_looks_blocked(page)) is False


def test_probe_failure_is_not_treated_as_a_block():
    class Broken:
        async def evaluate(self, _):
            raise RuntimeError("target closed")

    assert _run(common._page_looks_blocked(Broken())) is False


# ---------------------------------------------------------------------------
# Retry policy
# ---------------------------------------------------------------------------

def _attempts_recorder(results):
    """Returns an attempt_fn yielding the given results in order, plus a counter."""
    calls = {"n": 0}

    async def attempt():
        calls["n"] += 1
        return results[min(calls["n"] - 1, len(results) - 1)]

    return attempt, calls


def test_empty_is_not_retried():
    """The API already answered; asking again just burns another timeout."""
    attempt, calls = _attempts_recorder([common.ScrapeResult([], common.EMPTY)])
    _run(common.run_search(None, "milk", attempt, tag="T"))
    assert calls["n"] == 1


def test_blocked_is_retried():
    """WAF challenges are usually negotiated on the next load, not a standing ban."""
    attempt, calls = _attempts_recorder([
        common.ScrapeResult([], common.BLOCKED),
        common.ScrapeResult([{"name": "Amul Milk", "id": "1"}], common.OK),
    ])
    result = _run(common.run_search(None, "milk", attempt, tag="T"))
    assert calls["n"] == 2
    assert result.status == common.OK and len(result.products) == 1


def test_timeout_is_retried():
    attempt, calls = _attempts_recorder([
        common.ScrapeResult([], common.TIMEOUT),
        common.ScrapeResult([{"name": "Amul Milk", "id": "1"}], common.OK),
    ])
    assert _run(common.run_search(None, "milk", attempt, tag="T")).status == common.OK
    assert calls["n"] == 2


def test_success_stops_immediately():
    attempt, calls = _attempts_recorder([
        common.ScrapeResult([{"name": "Amul Milk", "id": "1"}], common.OK)
    ])
    _run(common.run_search(None, "milk", attempt, tag="T"))
    assert calls["n"] == 1


def test_raising_attempt_becomes_an_error_result():
    async def attempt():
        raise RuntimeError("boom")

    result = _run(common.run_search(None, "milk", attempt, tag="T"))
    assert result.status == common.ERROR
    assert "boom" in result.message


def test_ok_with_no_products_is_downgraded_to_empty():
    attempt, _ = _attempts_recorder([common.ScrapeResult([], common.OK)])
    assert _run(common.run_search(None, "milk", attempt, tag="T")).status == common.EMPTY


def test_results_are_capped_at_max_products():
    many = [{"name": f"Milk {i}", "id": str(i)} for i in range(30)]
    attempt, _ = _attempts_recorder([common.ScrapeResult(many, common.OK)])
    result = _run(common.run_search(None, "milk", attempt, tag="T"))
    assert len(result.products) == common.MAX_PRODUCTS


# The literal markup that caused the false positive: Swiggy serves this on
# healthy pages. Guards the regression independently of how detection is
# implemented, so a revert to raw-HTML scanning fails here too.
_HEALTHY_SWIGGY_HTML = (
    '<script type="text/javascript" '
    'src="https://b67f7794189c.edge.sdk.awswaf.com/b67f7794189c/5504ea1b6187/challenge.js">'
    '</script><div id="root">Amul Gold Full Cream Milk</div>'
)


def test_waf_sdk_script_matches_no_block_phrase():
    """Loading a WAF SDK is not being blocked by it."""
    low = _HEALTHY_SWIGGY_HTML.lower()
    matched = [p for p in common._BLOCK_PHRASES if p in low]
    assert matched == [], f"benign WAF SDK markup matched block phrases: {matched}"


def test_block_phrases_are_specific_enough_to_be_phrases():
    """Single vendor/product names are too broad to identify a challenge."""
    for phrase in common._BLOCK_PHRASES:
        assert " " in phrase, f"{phrase!r} is a bare token, not a challenge phrase"
