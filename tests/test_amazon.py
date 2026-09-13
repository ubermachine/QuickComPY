"""Tests for the Amazon.in scraper's pure parsing helpers.

No browser, no network -- these cover the shapes Amazon's markup actually
produced during development.
"""

import os
import sys

_project_root = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import pytest
from zendriver.core.connection import ProtocolException

from backend_py.scrapers import amazon


# ---------------------------------------------------------------------------
# Pincode resolution
# ---------------------------------------------------------------------------

def test_six_digit_pincode_passes_through():
    assert amazon.resolve_pincode("560001") == "560001"


def test_city_name_maps_to_a_pincode():
    assert amazon.resolve_pincode("Mumbai") == "400001"
    assert amazon.resolve_pincode("bengaluru") == "560001"


def test_unknown_location_falls_back():
    assert amazon.resolve_pincode("Atlantis") == amazon.DEFAULT_PINCODE
    assert amazon.resolve_pincode("") == amazon.DEFAULT_PINCODE
    assert amazon.resolve_pincode(None) == amazon.DEFAULT_PINCODE


def test_five_digit_number_is_not_a_pincode():
    """Indian pincodes are exactly six digits."""
    assert amazon.resolve_pincode("12345") == amazon.DEFAULT_PINCODE


# ---------------------------------------------------------------------------
# set_location
# ---------------------------------------------------------------------------

_ACCEPTED = '{"status": 200, "updated": true, "successful": true, "city": "GREATER NOIDA"}'


class LandingPage:
    """A tab whose first `navigations` address-change calls a redirect cuts off."""

    def __init__(self, navigations):
        self.navigations = navigations
        self.address_calls = 0

    async def get(self, url, **_kw):
        return self

    async def evaluate(self, expression, **_kw):
        if expression.startswith("!!("):
            return True  # common.wait_for's readiness probe
        self.address_calls += 1
        if self.address_calls <= self.navigations:
            raise ProtocolException(
                {"message": "Inspected target navigated or closed", "code": -32000}
            )
        return _ACCEPTED


async def test_set_location_survives_the_landing_page_redirect():
    """Seen live: the redirect landing mid-call left a flaky [ERR] Amazon badge."""
    page = LandingPage(navigations=1)
    assert await amazon.set_location(page, "201306") is True
    assert page.address_calls == 2


async def test_set_location_gives_up_on_a_page_that_never_settles():
    page = LandingPage(navigations=99)
    assert await amazon.set_location(page, "201306") is False
    assert page.address_calls == amazon._NAVIGATION_RETRIES + 1


async def test_set_location_does_not_retry_an_unrelated_failure():
    class Broken(LandingPage):
        async def evaluate(self, expression, **_kw):
            if expression.startswith("!!("):
                return True
            self.address_calls += 1
            raise RuntimeError("connection lost")

    page = Broken(navigations=0)
    assert await amazon.set_location(page, "201306") is False
    assert page.address_calls == 1, "only a navigation is worth sending the call again for"


# ---------------------------------------------------------------------------
# Delivery promise
# ---------------------------------------------------------------------------

def test_prefers_the_fastest_promise_over_the_free_one():
    raw = "FREE delivery Mon, 31 AugOr fastest delivery Today 10 am - 2 pm"
    assert amazon._delivery_time(raw) == "Today 10 am - 2 pm"


def test_falls_back_to_the_free_promise():
    assert amazon._delivery_time("FREE delivery Mon, 31 Aug on first order") == "Mon, 31 Aug"


def test_delivery_defaults_when_absent():
    assert amazon._delivery_time("") == "Standard Delivery"
    assert amazon._delivery_time(None) == "Standard Delivery"


# ---------------------------------------------------------------------------
# Quantity from the title
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("title,expected", [
    ("GAVYRATAN A2 Cow Skimmed Milk Powder 1kg | All Natural", "1kg"),
    ("NIVEA Nourishing Body Milk 600ml Body Lotion", "600ml"),
    ("Urban Platter Almond Milk, 1 Litre (Unsweetened)", "1 Litre"),
])
def test_quantity_extracted_from_title(title, expected):
    assert amazon._quantity(title) == expected


def test_quantity_defaults_when_title_has_no_size():
    assert amazon._quantity("Amazon Echo Dot") == "1 item"


# ---------------------------------------------------------------------------
# Card extraction
# ---------------------------------------------------------------------------

def _card(**kw):
    base = {
        "asin": "B000TEST", "title": "Amul Butter 500 g", "price": "₹540",
        "mrp": "₹700", "image": "https://example/i.jpg", "sponsored": False,
        "delivery": "FREE delivery Mon, 31 Aug", "unavailable": False,
    }
    base.update(kw)
    return base


def test_extract_builds_the_expected_shape():
    p = amazon.extract_products([_card()])[0]
    assert p["id"] == "az_B000TEST"
    assert p["name"] == "Amul Butter 500 g"
    assert p["price"] == "₹540"
    assert p["originalPrice"] == "₹700"
    assert p["savings"] == "₹160"
    assert p["discount"] == "23% OFF"
    assert p["quantity"] == "500 g"
    assert p["available"] is True
    assert p["source"] == "amazon"
    assert "sponsored" not in p, "internal flag must not leak into the API"


def test_comma_separated_mrp_is_parsed():
    p = amazon.extract_products([_card(price="₹525", mrp="₹1,050")])[0]
    assert p["originalPrice"] == "₹1050"
    assert p["discount"] == "50% OFF"


def test_sponsored_cards_are_dropped_when_organic_results_exist():
    cards = [
        _card(asin="AD1", title="Sponsored Ad - Brawny Bear Peanut Butter", sponsored=True),
        _card(asin="ORG1", title="Amul Butter 500 g"),
    ]
    names = [p["name"] for p in amazon.extract_products(cards)]
    assert names == ["Amul Butter 500 g"]


def test_sponsored_cards_are_kept_when_they_are_all_there_is():
    """Better a paid placement than an empty column."""
    cards = [_card(asin="AD1", title="Sponsored Ad - Brawny Bear Peanut Butter", sponsored=True)]
    products = amazon.extract_products(cards)
    assert len(products) == 1
    # The "Sponsored Ad - " prefix is stripped from the alt text.
    assert products[0]["name"] == "Brawny Bear Peanut Butter"


def test_cards_without_a_title_are_skipped():
    assert amazon.extract_products([_card(title="")]) == []


def test_missing_price_does_not_raise():
    p = amazon.extract_products([_card(price=None, mrp=None)])[0]
    assert p["price"] == "N/A"
    assert p["originalPrice"] is None


def test_unavailable_flag_is_carried_through():
    assert amazon.extract_products([_card(unavailable=True)])[0]["available"] is False
