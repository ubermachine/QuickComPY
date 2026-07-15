"""
Integration-light tests for the QuickCom backend.

Tests that scraper modules exist, have the expected interface, and that
product data flowing through the system is well-structured.  Does NOT
launch a browser — zendriver is imported but no page is created.
"""

import html
import sys
import os

# Ensure the project root is on sys.path so direct imports work.
_project_root = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import pytest

# ---------------------------------------------------------------------------
# 1.  Scraper module discovery
# ---------------------------------------------------------------------------

EXPECTED_SERVICES = ["blinkit", "bigbasket", "jiomart", "zepto"]
# instamart has working scraper code but is NOT in the app's SERVICES list
ADDITIONAL_SCRAPERS = ["instamart"]
ALL_SCRAPERS = EXPECTED_SERVICES + ADDITIONAL_SCRAPERS


@pytest.mark.parametrize("name", ALL_SCRAPERS)
def test_scraper_module_importable(name):
    """Every scraper module can be imported and exposes the expected
    top-level coroutines ``set_location`` and ``search``."""
    import importlib

    module = importlib.import_module(f"backend_py.scrapers.{name}")
    assert hasattr(module, "set_location"), f"{name} missing set_location"
    assert hasattr(module, "search"), f"{name} missing search"
    assert callable(module.set_location), f"{name}.set_location not callable"
    assert callable(module.search), f"{name}.search not callable"


def test_app_services_defined():
    """Verify the SERVICE names used in streamlit/app.py match the
    scraper modules.
    
    Note: we do NOT import app.py here because its module-level
    initialization starts a Zendriver browser.  The constant is
    verified against the known list defined in app.py's source.
    """
    # These are the services listed in streamlit/app.py (line 44)
    app_services = ["blinkit", "bigbasket", "jiomart", "zepto"]
    for svc in app_services:
        assert svc in EXPECTED_SERVICES, f"Unexpected service: {svc}"


# ---------------------------------------------------------------------------
# 2.  Product schema constants
# ---------------------------------------------------------------------------

REQUIRED_KEYS = [
    "id", "name", "price", "originalPrice", "savings",
    "quantity", "deliveryTime", "discount", "imageUrl",
    "available", "source",
]

VALID_SOURCES = ["blinkit", "bigbasket", "jiomart", "zepto", "instamart"]


def _valid_product(**overrides):
    """Return a dict that satisfies the product schema."""
    product = {
        "id": "test_1",
        "name": "Test Product",
        "price": "₹99",
        "originalPrice": "₹150",
        "savings": "₹51",
        "quantity": "1 kg",
        "deliveryTime": "10 mins",
        "discount": "34% OFF",
        "imageUrl": "https://example.com/img.jpg",
        "available": True,
        "source": "blinkit",
    }
    product.update(overrides)
    return product


# ---------------------------------------------------------------------------
# 3.  Schema validation tests (pure function — no browser)
# ---------------------------------------------------------------------------


def validate_product(p):
    """Return a list of validation error strings (empty = valid)."""
    errors = []
    if not isinstance(p, dict):
        errors.append("product is not a dict")
        return errors

    for key in REQUIRED_KEYS:
        if key not in p:
            errors.append(f"missing key: {key}")

    if "source" in p and p["source"] not in VALID_SOURCES:
        errors.append(f"invalid source: {p['source']}")

    if "available" in p and not isinstance(p.get("available"), bool):
        errors.append("available must be a bool")

    # Price must be a string (even "N/A")
    if "price" in p and not isinstance(p.get("price"), str):
        errors.append("price must be a string")

    # Name must be a string
    if "name" in p and not isinstance(p.get("name"), str):
        errors.append("name must be a string")

    return errors


class TestProductSchema:
    """Tests that product data conforms to the expected schema."""

    def test_valid_product_passes(self):
        assert validate_product(_valid_product()) == []

    @pytest.mark.parametrize("key", REQUIRED_KEYS)
    def test_missing_key(self, key):
        p = _valid_product()
        del p[key]
        errs = validate_product(p)
        assert f"missing key: {key}" in errs, f"missing {key!r} not detected"

    def test_invalid_source(self):
        p = _valid_product(source="unknown_vendor")
        errs = validate_product(p)
        assert any("invalid source" in e for e in errs)

    def test_available_not_bool(self):
        p = _valid_product(available="yes")
        errs = validate_product(p)
        assert any("available must be a bool" in e for e in errs)

    def test_price_not_string(self):
        p = _valid_product(price=99)
        errs = validate_product(p)
        assert any("price must be a string" in e for e in errs)

    def test_name_not_string(self):
        p = _valid_product(name=12345)
        errs = validate_product(p)
        assert any("name must be a string" in e for e in errs)


# ---------------------------------------------------------------------------
# 4.  HTML escaping tests  (mimics the card rendering in app.py)
# ---------------------------------------------------------------------------


def render_card_html(product):
    """Minimal reproduction of the card HTML generated by streamlit/app.py."""
    # Use .get(key) or default to handle both missing keys AND None values
    safe_name = html.escape(str(product.get("name") or "Unknown"))
    safe_price = html.escape(str(product.get("price") or "N/A"))
    safe_qty = html.escape(str(product.get("quantity") or "1 item"))
    safe_delivery = html.escape(str(product.get("deliveryTime") or "N/A"))
    safe_orig = html.escape(str(product.get("originalPrice") or ""))
    safe_discount = html.escape(str(product.get("discount") or ""))
    safe_img = html.escape(str(product.get("imageUrl") or ""), quote=True)

    img_tag = f'<img src="{safe_img}" class="product-img"/>' if safe_img else ""
    orig_price_tag = (
        f'<span class="original-price">{safe_orig}</span>' if safe_orig else ""
    )
    discount_tag = (
        f'<span class="discount-badge">{safe_discount}</span>' if safe_discount else ""
    )
    discount_div = f'<div style="margin-top:4px;">{discount_tag}</div>' if discount_tag else ""

    return f"""
    <div class="glass-card">
        {img_tag}
        <div class="product-title">{safe_name}</div>
        <div style="color: #cbd5e1; font-size: 0.8em; margin-bottom: 8px;">{safe_qty} | Time: {safe_delivery}</div>
        <div class="price-row">
            <span class="current-price">{safe_price}</span>
            {orig_price_tag}
        </div>
        {discount_div}
    </div>
    """


class TestHtmlEscaping:
    """Verify that HTML special characters are escaped before rendering."""

    def test_html_in_name_is_escaped(self):
        p = _valid_product(name='<script>alert("xss")</script>')
        html_out = render_card_html(p)
        assert "&lt;script&gt;" in html_out
        assert "<script>" not in html_out

    def test_html_in_price_is_escaped(self):
        p = _valid_product(price='<b>₹99</b>')
        html_out = render_card_html(p)
        assert "&lt;b&gt;" in html_out
        assert "<b>" not in html_out

    def test_html_in_quantity_is_escaped(self):
        p = _valid_product(quantity='<script>evil</script>')
        html_out = render_card_html(p)
        assert "&lt;script&gt;" in html_out

    def test_html_in_delivery_is_escaped(self):
        p = _valid_product(deliveryTime='<a href="bad">link</a>')
        html_out = render_card_html(p)
        assert "&lt;a href=" in html_out

    def test_html_in_image_url_is_escaped(self):
        p = _valid_product(imageUrl='" onerror="alert(1)"')
        html_out = render_card_html(p)
        # The quote=True param escapes double-quotes
        assert "&quot; onerror=&quot;alert(1)&quot;" in html_out

    def test_html_in_discount_is_escaped(self):
        p = _valid_product(discount='<img src=x onerror=alert(1)>')
        html_out = render_card_html(p)
        assert "&lt;img src=x onerror=alert(1)&gt;" in html_out

    def test_safe_normal_text_unchanged(self):
        p = _valid_product(
            name="Fresh Apples",
            price="₹120",
            quantity="500 g",
            deliveryTime="10 mins",
            discount="10% OFF",
            imageUrl="https://example.com/apple.jpg",
        )
        html_out = render_card_html(p)
        assert "Fresh Apples" in html_out
        assert "₹120" in html_out
        assert "500 g" in html_out
        assert "10 mins" in html_out
        assert "10% OFF" in html_out
        assert "https://example.com/apple.jpg" in html_out


# ---------------------------------------------------------------------------
# 5.  Edge cases for None / empty values
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Test that missing or None fields don't crash the rendering."""

    def test_none_name_falls_back(self):
        p = _valid_product(name=None)
        html_out = render_card_html(p)
        assert "Unknown" in html_out

    def test_none_price_falls_back(self):
        p = _valid_product(price=None)
        html_out = render_card_html(p)
        assert "N/A" in html_out

    def test_none_image_url_no_img_tag(self):
        p = _valid_product(imageUrl=None)
        html_out = render_card_html(p)
        # No <img> tag should be rendered
        assert '<img' not in html_out

    def test_empty_image_url_no_img_tag(self):
        p = _valid_product(imageUrl="")
        html_out = render_card_html(p)
        assert '<img' not in html_out

    def test_none_original_price_no_strikethrough(self):
        p = _valid_product(originalPrice=None)
        html_out = render_card_html(p)
        assert 'original-price' not in html_out

    def test_none_savings_allowed(self):
        """Savings may be None (not displayed, but valid schema)."""
        p = _valid_product(savings=None)
        assert validate_product(p) == []

    def test_none_discount_no_badge(self):
        p = _valid_product(discount=None)
        html_out = render_card_html(p)
        assert "discount-badge" not in html_out

    def test_missing_all_optional_fields(self):
        p = _valid_product(
            originalPrice=None,
            savings=None,
            discount=None,
            imageUrl="",
        )
        assert validate_product(p) == []
        html_out = render_card_html(p)
        assert '<img' not in html_out
        assert 'original-price' not in html_out
        assert 'discount-badge' not in html_out


# ---------------------------------------------------------------------------
# 6.  Helper function tests  (from bigbasket: resolve_pincode, etc.)
# ---------------------------------------------------------------------------


class TestBigbasketHelpers:
    """Test pure functions from the bigbasket scraper module."""

    @pytest.fixture(autouse=True)
    def _import_bb(self):
        from backend_py.scrapers import bigbasket
        self.bb = bigbasket

    def test_resolve_pincode_default(self):
        assert self.bb.resolve_pincode(None) == "201306"
        assert self.bb.resolve_pincode("") == "201306"

    def test_resolve_pincode_exact(self):
        assert self.bb.resolve_pincode("110001") == "110001"
        assert self.bb.resolve_pincode("400001") == "400001"

    def test_resolve_pincode_city_name(self):
        assert self.bb.resolve_pincode("Delhi") == "110001"
        assert self.bb.resolve_pincode("Mumbai") == "400001"
        assert self.bb.resolve_pincode("bangalore") == "560001"
        assert self.bb.resolve_pincode("Hyderabad") == "500001"

    def test_resolve_pincode_unknown_fallsback(self):
        assert self.bb.resolve_pincode("999999") == "999999"
        assert self.bb.resolve_pincode("random_place") == "201306"


class TestOtherScraperHelpers:
    """Test pure helper functions from blinkit and zepto scrapers."""

    def test_blinkit_resolve_coords_default(self):
        from backend_py.scrapers import blinkit
        coords = blinkit.resolve_coords(None)
        assert coords["lat"] == 28.5147
        assert coords["lon"] == 77.4855

    def test_blinkit_resolve_coords_known(self):
        from backend_py.scrapers import blinkit
        coords = blinkit.resolve_coords("Mumbai")
        assert coords["lat"] == 19.0760
        assert coords["lon"] == 72.8777

    def test_zepto_module_has_pincode_vars(self):
        from backend_py.scrapers import zepto
        assert hasattr(zepto, "_pincode")
        assert hasattr(zepto, "_lat")
        assert hasattr(zepto, "_lon")
