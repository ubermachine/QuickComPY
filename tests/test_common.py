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


def test_run_search_returns_a_pool_not_just_the_visible_page():
    """The cap to MAX_PRODUCTS belongs to the view, not the scrape.

    run_search keeps up to POOL_SIZE candidates so the API layer can sort or
    filter across them; trimming to eight here would hide the best discount
    whenever it ranks ninth or lower on relevance.
    """
    many = [{"name": f"Milk {i}", "id": str(i)} for i in range(30)]
    attempt, _ = _attempts_recorder([common.ScrapeResult(many, common.OK)])
    result = _run(common.run_search(None, "milk", attempt, tag="T"))
    assert len(result.products) == 30
    assert common.apply_view(result.products) == result.products[:common.MAX_PRODUCTS]


def test_run_search_caps_the_pool():
    many = [{"name": f"Milk {i}", "id": str(i)} for i in range(200)]
    attempt, _ = _attempts_recorder([common.ScrapeResult(many, common.OK)])
    result = _run(common.run_search(None, "milk", attempt, tag="T"))
    assert len(result.products) == common.POOL_SIZE


def test_run_search_annotates_discounts():
    """Downstream sorting needs the numeric field to already be present."""
    products = [{"name": "Amul Milk", "id": "1", "price": "₹75", "originalPrice": "₹100"}]
    attempt, _ = _attempts_recorder([common.ScrapeResult(products, common.OK)])
    result = _run(common.run_search(None, "milk", attempt, tag="T"))
    assert result.products[0]["discountPercent"] == 25.0


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


# ---------------------------------------------------------------------------
# Discount percentage, filtering and sorting
# ---------------------------------------------------------------------------

def _p(name, price=None, orig=None, discount=None):
    return {"name": name, "price": price, "originalPrice": orig, "discount": discount}


def test_discount_percent_computed_from_prices():
    assert common.discount_percent(_p("A", "₹180", "₹240")) == 25.0


def test_discount_percent_prefers_arithmetic_over_platform_copy():
    """Platform copy is inconsistent; price vs MRP is not."""
    p = _p("A", "₹180", "₹240", discount="SAVE 70%")
    assert common.discount_percent(p) == 25.0


def test_discount_percent_falls_back_to_copy_without_mrp():
    assert common.discount_percent(_p("A", "₹100", None, "47% OFF")) == 47.0


def test_discount_percent_zero_without_any_signal():
    assert common.discount_percent(_p("A", "₹100")) == 0.0
    assert common.discount_percent(_p("A", "₹100", None, "Buy 1 Get 1")) == 0.0


def test_discount_percent_ignores_nonsense_copy():
    """A "100% natural" claim is not a discount."""
    assert common.discount_percent(_p("A", "₹100", None, "100% Natural")) == 0.0


def test_discount_percent_handles_comma_separated_prices():
    assert common.discount_percent(_p("A", "₹525", "₹1,050")) == 50.0


def test_annotate_discounts_adds_the_field_to_every_product():
    products = [_p("A", "₹180", "₹240"), _p("B", "₹50")]
    common.annotate_discounts(products)
    assert [p["discountPercent"] for p in products] == [25.0, 0.0]


def test_default_view_preserves_relevance_order():
    """The normal search must behave exactly as before."""
    products = common.annotate_discounts([
        _p("A", "₹90", "₹100"), _p("B", "₹10", "₹100"), _p("C", "₹99", "₹100"),
    ])
    assert _names(common.apply_view(products, limit=None)) == ["A", "B", "C"]


def test_sort_by_discount_orders_biggest_first():
    products = common.annotate_discounts([
        _p("A", "₹90", "₹100"), _p("B", "₹10", "₹100"), _p("C", "₹50", "₹100"),
    ])
    view = common.apply_view(products, sort=common.SORT_DISCOUNT, limit=None)
    assert _names(view) == ["B", "C", "A"]


def test_sort_by_discount_is_stable_within_equal_discounts():
    products = common.annotate_discounts([
        _p("First", "₹50", "₹100"), _p("Second", "₹50", "₹100"),
    ])
    view = common.apply_view(products, sort=common.SORT_DISCOUNT, limit=None)
    assert _names(view) == ["First", "Second"]


def test_min_discount_filters_out_weaker_offers():
    products = common.annotate_discounts([
        _p("A", "₹90", "₹100"), _p("B", "₹10", "₹100"), _p("C", "₹50", "₹100"),
    ])
    view = common.apply_view(products, min_discount=40, limit=None)
    assert _names(view) == ["B", "C"]


def test_min_discount_can_exclude_everything():
    products = common.annotate_discounts([_p("A", "₹90", "₹100")])
    assert common.apply_view(products, min_discount=50, limit=None) == []


def test_filter_and_sort_compose():
    products = common.annotate_discounts([
        _p("A", "₹90", "₹100"), _p("B", "₹10", "₹100"),
        _p("C", "₹50", "₹100"), _p("D", "₹25", "₹100"),
    ])
    view = common.apply_view(products, sort=common.SORT_DISCOUNT, min_discount=40, limit=None)
    assert _names(view) == ["B", "D", "C"]


def test_view_respects_the_limit():
    products = common.annotate_discounts([_p(f"P{i}", "₹50", "₹100") for i in range(30)])
    assert len(common.apply_view(products, limit=common.MAX_PRODUCTS)) == common.MAX_PRODUCTS


def test_sorting_by_discount_can_reach_past_the_visible_eight():
    """The whole point of the pool: the best deal may rank low on relevance."""
    products = common.annotate_discounts(
        [_p(f"Relevant {i}", "₹99", "₹100") for i in range(8)]
        + [_p("Deep Bargain", "₹10", "₹100")]
    )
    view = common.apply_view(products, sort=common.SORT_DISCOUNT, limit=common.MAX_PRODUCTS)
    assert view[0]["name"] == "Deep Bargain"


def test_pool_is_larger_than_the_visible_page():
    assert common.POOL_SIZE > common.MAX_PRODUCTS


# ---------------------------------------------------------------------------
# wait_for / warmup gating
# ---------------------------------------------------------------------------

class _PredicatePage:
    """Returns False for the first `flips` polls, then True."""

    def __init__(self, flips=0, raises=False):
        self.flips = flips
        self.raises = raises
        self.calls = 0

    async def evaluate(self, _expression):
        self.calls += 1
        if self.raises:
            raise RuntimeError("page gone")
        return self.calls > self.flips


def test_wait_for_returns_immediately_when_already_true():
    page = _PredicatePage()
    assert _run(common.wait_for(page, "x", timeout=2)) is True
    assert page.calls == 1


def test_wait_for_polls_until_true():
    page = _PredicatePage(flips=2)
    assert _run(common.wait_for(page, "x", timeout=3, interval=0.01)) is True
    assert page.calls == 3


def test_wait_for_gives_up_and_reports_false():
    page = _PredicatePage(flips=10_000)
    assert _run(common.wait_for(page, "x", timeout=0.1, interval=0.01)) is False


def test_wait_for_survives_an_evaluate_error():
    assert _run(common.wait_for(_PredicatePage(raises=True), "x", timeout=0.1, interval=0.01)) is False


class _CookiePage:
    def __init__(self, cookies):
        self._cookies = cookies

    async def send(self, _cmd):
        if self._cookies is None:
            raise RuntimeError("cdp failed")
        return self._cookies


def test_warmup_skipped_when_the_origin_already_has_cookies():
    """The measured win: skipping a redundant homepage load per search."""
    assert _run(common._needs_warmup(_CookiePage(["a-cookie"]), "https://x.test")) is False


def test_warmup_needed_when_no_cookies_yet():
    assert _run(common._needs_warmup(_CookiePage([]), "https://x.test")) is True


def test_warmup_needed_when_the_check_itself_fails():
    """Take the fast path only on positive evidence."""
    assert _run(common._needs_warmup(_CookiePage(None), "https://x.test")) is True
