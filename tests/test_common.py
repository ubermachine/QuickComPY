"""Tests for the shared scraping helpers in backend_py/scrapers/common.py.

Pure functions only -- no browser, no network.
"""

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
