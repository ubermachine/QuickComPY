"""Tests for JioMart's location resolution and payload parsing.

No browser, no network.
"""

import os
import sys

_project_root = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import pytest

from backend_py.scrapers import jiomart


# ---------------------------------------------------------------------------
# Pincode resolution
# ---------------------------------------------------------------------------

def test_known_pincode_passes_through():
    assert jiomart.resolve_pincode("400001") == "400001"


def test_city_name_maps_to_a_pincode():
    assert jiomart.resolve_pincode("Mumbai") == "400001"
    assert jiomart.resolve_pincode("bengaluru") == "560001"


def test_unknown_location_falls_back():
    assert jiomart.resolve_pincode("Atlantis") == jiomart.DEFAULT_PINCODE
    assert jiomart.resolve_pincode(None) == jiomart.DEFAULT_PINCODE


def test_unmapped_pincode_falls_back():
    """Every pincode we accept must have coordinates to send with it."""
    assert jiomart.resolve_pincode("999999") == jiomart.DEFAULT_PINCODE


def test_every_pincode_has_complete_location_data():
    for pin, entry in jiomart.LOCATIONS.items():
        city, state, lat, lng = entry
        assert pin.isdigit() and len(pin) == 6
        assert city and state
        assert float(lat) and float(lng)


def test_every_city_alias_points_at_a_known_pincode():
    for city, pin in jiomart.CITY_PINCODES.items():
        assert pin in jiomart.LOCATIONS, f"{city} -> {pin} has no coordinates"


# ---------------------------------------------------------------------------
# Pack size
# ---------------------------------------------------------------------------

def test_quantity_prefers_the_sizes_field():
    """Authoritative, and the title regex cannot handle a trailing suffix."""
    item = {"sizes": ["1 L"]}
    assert jiomart._quantity(item, "Gokul Full Cream Milk 1 L (Pouch)") == "1 L"


def test_quantity_reads_structured_net_quantity():
    item = {"net_quantity": {"unit": "ml", "value": 500}}
    assert jiomart._quantity(item, "Anything") == "500 ml"


def test_quantity_falls_back_to_the_title():
    assert jiomart._quantity({}, "Amul Taaza Toned Milk 500 ml") == "500 ml"


def test_quantity_defaults_when_nothing_is_available():
    assert jiomart._quantity({}, "Amazon Echo") == "1 item"


def test_size_regex_has_no_stray_control_characters():
    """Guards a real bug: a literal backspace once replaced \\b and silently
    broke every title-derived pack size."""
    pattern = jiomart._SIZE_RE.pattern
    assert not [c for c in pattern if ord(c) < 32], repr(pattern)


# ---------------------------------------------------------------------------
# Product extraction
# ---------------------------------------------------------------------------

def _item(**kw):
    base = {
        "name": "Amul Gold Full Cream Milk 1 L (Pouch)",
        "uid": 7535057,
        "price": {"effective": {"min": 71}, "marked": {"min": 90}},
        "medias": [{"url": "https://cdn/x.jpg"}],
        "sellable": True,
        "sizes": ["1 L"],
    }
    base.update(kw)
    return base


def test_extract_builds_the_expected_shape():
    p = jiomart.extract_products([_item()])[0]
    assert p["id"] == "jm_7535057"
    assert p["price"] == "₹71"
    assert p["originalPrice"] == "₹90"
    assert p["quantity"] == "1 L"
    assert p["available"] is True
    assert p["source"] == "jiomart"


def test_extract_skips_items_without_a_name():
    assert jiomart.extract_products([_item(name="")]) == []


def test_extract_survives_a_malformed_item():
    """One bad row must not lose the whole page."""
    products = jiomart.extract_products([{"name": "Broken", "price": "not-a-dict"}, _item()])
    assert [p["name"] for p in products] == ["Amul Gold Full Cream Milk 1 L (Pouch)"]


def test_unsellable_items_are_marked_unavailable():
    assert jiomart.extract_products([_item(sellable=False)])[0]["available"] is False
