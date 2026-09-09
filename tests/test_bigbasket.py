"""Tests for BigBasket's payload parsing.

No browser, no network.
"""

import os
import sys

_project_root = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import pytest

from backend_py.scrapers import bigbasket


def _item(**kw):
    base = {
        "desc": "Gold Full Cream Milk",
        "id": 40147597,
        "brand": {"name": "Amul"},
        "pricing": {"discount": {"prim_price": {"sp": "120"}, "mrp": "150"}},
        "images": [{"m": "https://cdn/x.jpg"}],
        "w": "1 L",
        "availability": {"avail_status": "001", "short_eta": "10 mins"},
    }
    base.update(kw)
    return base


# ---------------------------------------------------------------------------
# Delivery ETA
#
# Regression guard: an earlier version read bb_now_eta and delivery_info.eta,
# neither of which BigBasket sends, so every row showed "Standard Delivery"
# while the other five platforms displayed real minutes. The promise actually
# lives in availability.short_eta.
# ---------------------------------------------------------------------------

def test_express_eta_is_read_from_availability():
    assert bigbasket.extract_products([_item()])[0]["deliveryTime"] == "10 mins"


def test_eta_falls_back_when_absent():
    item = _item(availability={"avail_status": "001"})
    assert bigbasket.extract_products([item])[0]["deliveryTime"] == "Standard Delivery"


# ---------------------------------------------------------------------------
# Availability
# ---------------------------------------------------------------------------

def test_in_stock_status_is_available():
    assert bigbasket.extract_products([_item()])[0]["available"] is True


def test_other_statuses_are_unavailable():
    item = _item(availability={"avail_status": "002", "short_eta": "10 mins"})
    assert bigbasket.extract_products([item])[0]["available"] is False


def test_missing_availability_defaults_to_in_stock():
    """A search result with no availability block is assumed sellable."""
    item = _item(availability={})
    assert bigbasket.extract_products([item])[0]["available"] is True


# ---------------------------------------------------------------------------
# Naming, price and shape
# ---------------------------------------------------------------------------

def test_brand_is_prefixed_when_missing_from_the_description():
    assert bigbasket.extract_products([_item()])[0]["name"] == "Amul Gold Full Cream Milk"


def test_brand_is_not_duplicated():
    item = _item(desc="Amul Gold Full Cream Milk")
    assert bigbasket.extract_products([item])[0]["name"] == "Amul Gold Full Cream Milk"


def test_price_fields_are_derived():
    p = bigbasket.extract_products([_item()])[0]
    assert p["price"] == "₹120"
    assert p["originalPrice"] == "₹150"
    assert p["savings"] == "₹30"
    assert p["discount"] == "20% OFF"


def test_quantity_comes_from_the_weight_field():
    assert bigbasket.extract_products([_item()])[0]["quantity"] == "1 L"


def test_items_without_a_description_are_skipped():
    assert bigbasket.extract_products([_item(desc="")]) == []


def test_a_malformed_item_does_not_lose_the_page():
    products = bigbasket.extract_products([{"desc": "Broken", "pricing": "nonsense"}, _item()])
    assert [p["name"] for p in products] == ["Amul Gold Full Cream Milk"]


def test_source_is_tagged():
    assert bigbasket.extract_products([_item()])[0]["source"] == "bigbasket"
