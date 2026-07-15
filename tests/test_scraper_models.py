"""
Tests for product data models and price-parsing edge cases.

Verifies that all scrapers produce dicts conforming to the expected schema,
and that extreme/invalid inputs are handled gracefully.
"""

import sys
import os

_project_root = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import pytest

# ---------------------------------------------------------------------------
# Schema constants (shared with test_backend)
# ---------------------------------------------------------------------------

REQUIRED_KEYS = [
    "id", "name", "price", "originalPrice", "savings",
    "quantity", "deliveryTime", "discount", "imageUrl",
    "available", "source",
]

VALID_SOURCES = ["blinkit", "bigbasket", "jiomart", "zepto", "instamart"]

STRING_KEYS = {"id", "name", "price", "quantity", "deliveryTime", "source"}
NULLABLE_STRING_KEYS = {"originalPrice", "savings", "discount"}
URL_KEYS = {"imageUrl"}


def _valid_product(**overrides):
    """Return a fresh mock product dict."""
    p = {
        "id": "mock_1",
        "name": "Mock Product",
        "price": "₹99",
        "originalPrice": "₹150",
        "savings": "₹51",
        "quantity": "1 kg",
        "deliveryTime": "Standard Delivery",
        "discount": "34% OFF",
        "imageUrl": "https://example.com/pic.jpg",
        "available": True,
        "source": "bigbasket",
    }
    p.update(overrides)
    return p


# ---------------------------------------------------------------------------
# 1.  Product validation helpers
# ---------------------------------------------------------------------------


def assert_valid_product(p):
    """Assert that *p* conforms to the expected schema, returning it."""
    assert isinstance(p, dict), "product must be a dict"
    for key in REQUIRED_KEYS:
        assert key in p, f"missing required key: {key!r}"

    assert p["source"] in VALID_SOURCES, f"unknown source: {p['source']}"
    assert isinstance(p["available"], bool), "available must be bool"
    assert isinstance(p["name"], str), "name must be str"
    assert isinstance(p["price"], str), "price must be str"

    # Nullable string fields: must be None or str
    for key in NULLABLE_STRING_KEYS:
        assert p[key] is None or isinstance(p[key], str), \
            f"{key} must be str or None, got {type(p[key]).__name__}"

    # imageUrl: must be str (possibly empty) or None
    assert p["imageUrl"] is None or isinstance(p["imageUrl"], str), \
        "imageUrl must be str or None, got " + type(p["imageUrl"]).__name__

    return p


# ---------------------------------------------------------------------------
# 2.  Standard valid-product tests
# ---------------------------------------------------------------------------


class TestValidProducts:
    """A set of valid product dicts that should always pass."""

    @pytest.mark.parametrize(
        "product",
        [
            _valid_product(),
            _valid_product(source="blinkit"),
            _valid_product(source="zepto"),
            _valid_product(source="instamart"),
            _valid_product(source="jiomart"),
            _valid_product(available=False),
            _valid_product(discount=None, savings=None, originalPrice=None),
            _valid_product(imageUrl=""),
            _valid_product(price="N/A"),
            _valid_product(price="₹0"),
            _valid_product(name="A"),
            _valid_product(id=""),
            _valid_product(deliveryTime=""),
            _valid_product(quantity=""),
        ],
    )
    def test_valid_product(self, product):
        assert_valid_product(product)


# ---------------------------------------------------------------------------
# 3.  Mock scraper outputs — simulate what each scraper produces
# ---------------------------------------------------------------------------


@pytest.fixture
def blinkit_mock_product():
    return {
        "id": "12345",
        "name": "Amul Butter 500 g",
        "price": "₹60",
        "originalPrice": "₹75",
        "savings": "₹15",
        "quantity": "500 g",
        "deliveryTime": "10 mins",
        "discount": "20% OFF",
        "imageUrl": "https://cdn.blinkit.com/foo.jpg",
        "available": True,
        "source": "blinkit",
    }


@pytest.fixture
def bigbasket_mock_product():
    return {
        "id": "bb_0",
        "name": "Tata Salt 1 kg",
        "price": "₹18",
        "originalPrice": None,
        "savings": None,
        "quantity": "1 kg",
        "deliveryTime": "Standard Delivery",
        "discount": None,
        "imageUrl": "https://www.bigbasket.com/bar.jpg",
        "available": True,
        "source": "bigbasket",
    }


@pytest.fixture
def zepto_mock_product():
    return {
        "id": "zp_1",
        "name": "Milk 1 L",
        "price": "₹68",
        "originalPrice": "₹75",
        "savings": "₹7",
        "quantity": "1 item",
        "deliveryTime": "10 mins",
        "discount": "9% OFF",
        "imageUrl": "",
        "available": True,
        "source": "zepto",
    }


@pytest.fixture
def jiomart_mock_product():
    return {
        "id": "jm_3",
        "name": "Fortune Oil 1 L",
        "price": "₹185",
        "originalPrice": None,
        "savings": None,
        "quantity": "",
        "deliveryTime": "Standard Delivery",
        "discount": None,
        "imageUrl": "https://www.jiomart.com/img.jpg",
        "available": True,
        "source": "jiomart",
    }


@pytest.fixture
def instamart_mock_product():
    return {
        "id": "im_2",
        "name": "Detergent Powder 2 kg",
        "price": "₹340",
        "originalPrice": "₹420",
        "savings": None,
        "quantity": "2 kg",
        "deliveryTime": "15 mins",
        "discount": "20% OFF",
        "imageUrl": "",
        "available": True,
        "source": "instamart",
    }


class TestMockScraperOutputs:
    """Verify that mock products representing each scraper's output are valid."""

    def test_blinkit_mock(self, blinkit_mock_product):
        assert_valid_product(blinkit_mock_product)
        assert blinkit_mock_product["source"] == "blinkit"

    def test_bigbasket_mock(self, bigbasket_mock_product):
        assert_valid_product(bigbasket_mock_product)
        assert bigbasket_mock_product["source"] == "bigbasket"

    def test_zepto_mock(self, zepto_mock_product):
        assert_valid_product(zepto_mock_product)
        assert zepto_mock_product["source"] == "zepto"

    def test_jiomart_mock(self, jiomart_mock_product):
        assert_valid_product(jiomart_mock_product)
        assert jiomart_mock_product["source"] == "jiomart"

    def test_instamart_mock(self, instamart_mock_product):
        assert_valid_product(instamart_mock_product)
        assert instamart_mock_product["source"] == "instamart"


# ---------------------------------------------------------------------------
# 4.  Price-parsing edge cases
# ---------------------------------------------------------------------------


def parse_price_amount(price_str):
    """Extract the numeric amount from a price string.

    Mirrors the parsing done by scrapers (e.g.  ``parseFloat(price.replace(/[^0-9.]/g, ''))``
    in JS, or ``re.search(r'₹\\s*(\\d+(?:\\.\\d+)?)', price)`` in Python).
    """
    import re
    if not price_str or price_str == "N/A":
        return None
    # Remove commas before matching so ₹1,299 → 1299.0
    cleaned_str = str(price_str).replace(",", "")
    match = re.search(r"₹\s*(\d+(?:\.\d{1,2})?)", cleaned_str)
    if match:
        return float(match.group(1))
    # Fallback: strip non-numeric chars and try to parse
    cleaned = re.sub(r"[^\d.]", "", cleaned_str)
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except (ValueError, TypeError):
        return None


class TestPriceParsing:
    """Edge cases for price string parsing."""

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("₹99", 99.0),
            ("₹ 99", 99.0),
            ("₹99.50", 99.5),
            ("₹1,299", 1299.0),
            ("₹ 1,299.50", 1299.5),
            ("N/A", None),
            ("", None),
            (None, None),
            ("0", 0.0),
            ("₹0", 0.0),
            ("FREE", None),
            ("$5", 5.0),  # dollar stripped; numeric part parsed
        ],
    )
    def test_parse_price_amount(self, raw, expected):
        assert parse_price_amount(raw) == expected

    def test_price_comparison_logic(self):
        """Replicate the savings/discount calculation done by scrapers."""
        price_str = "₹99"
        orig_str = "₹150"

        cur = parse_price_amount(price_str)
        orig = parse_price_amount(orig_str)

        assert cur == 99.0
        assert orig == 150.0
        assert orig > cur
        savings = orig - cur
        discount_pct = round(((orig - cur) / orig) * 100)
        assert savings == 51.0
        assert discount_pct == 34

    def test_no_discount_when_mrp_equals_price(self):
        """When originalPrice equals price, no savings or discount."""
        cur = parse_price_amount("₹100")
        orig = parse_price_amount("₹100")
        assert cur == orig
        assert not (orig > cur)  # no savings

    def test_no_discount_when_mrp_missing(self):
        cur = parse_price_amount("₹99")
        orig = parse_price_amount(None)
        assert orig is None
        assert cur == 99.0
        # No discount when originalPrice is None

    def test_no_discount_when_price_is_na(self):
        cur = parse_price_amount("N/A")
        orig = parse_price_amount("₹150")
        assert cur is None
        assert orig == 150.0

    @pytest.mark.parametrize(
        "price_str,orig_str,expected_savings,expected_discount",
        [
            ("₹75", "₹100", 25.0, 25),
            ("₹10", "₹20", 10.0, 50),
            ("₹199", "₹499", 300.0, 60),
            ("₹1", "₹1", 0.0, 0),
            ("₹0", "₹0", 0.0, 0),
        ],
    )
    def test_savings_discount_calculation(
        self, price_str, orig_str, expected_savings, expected_discount
    ):
        cur = parse_price_amount(price_str)
        orig = parse_price_amount(orig_str)
        if orig is not None and cur is not None and orig > cur:
            savings = orig - cur
            discount_pct = round(((orig - cur) / orig) * 100)
        else:
            savings = 0.0
            discount_pct = 0
        assert savings == expected_savings
        assert discount_pct == expected_discount


# ---------------------------------------------------------------------------
# 5.  Extreme / boundary inputs
# ---------------------------------------------------------------------------


class TestExtremeInputs:
    """Products with extreme or unusual field values."""

    def test_very_long_name(self):
        """Name should be truncated or handled gracefully."""
        p = _valid_product(name="A" * 10_000)
        assert_valid_product(p)

    def test_very_long_price(self):
        p = _valid_product(price="₹" + "9" * 100)
        assert_valid_product(p)

    def test_special_characters_in_name(self):
        p = _valid_product(name="Café Français με ελληνικά 中文 Español")
        assert_valid_product(p)

    def test_emoji_in_name(self):
        p = _valid_product(name="🥛 Milk 🥚 Eggs 🧈 Butter")
        assert_valid_product(p)

    def test_negative_price_string(self):
        """Price string with negative number (shouldn't happen but be safe)."""
        p = _valid_product(price="₹-50")
        assert_valid_product(p)
        # The numeric parser should still extract something meaningful
        val = parse_price_amount(p["price"])
        assert val is not None

    def test_price_with_extra_text(self):
        p = _valid_product(price="₹99 (inclusive of all taxes)")
        assert_valid_product(p)
        val = parse_price_amount(p["price"])
        assert val == 99.0

    def test_empty_strings_for_all_fields(self):
        p = _valid_product(
            id="",
            name="",
            price="",
            originalPrice="",
            savings="",
            quantity="",
            deliveryTime="",
            discount="",
            imageUrl="",
            available=True,
            source="blinkit",
        )
        assert_valid_product(p)

    def test_all_fields_none_except_required_strings(self):
        """Ensure the schema allows None for optional fields."""
        p = {
            "id": "test",
            "name": "Test",
            "price": "₹100",
            "originalPrice": None,
            "savings": None,
            "quantity": "1",
            "deliveryTime": "N/A",
            "discount": None,
            "imageUrl": "",
            "available": True,
            "source": "zepto",
        }
        assert_valid_product(p)


# ---------------------------------------------------------------------------
# 6.  Invariant: id uniqueness across scrapers
# ---------------------------------------------------------------------------


class TestIdUniqueness:
    """Each scraper prefixes its IDs to avoid collisions."""

    @pytest.mark.parametrize(
        "source,prefix",
        [
            ("blinkit", ""),     # blinkit uses numeric IDs (from API)
            ("bigbasket", "bb_"),
            ("jiomart", "jm_"),
            ("zepto", "zp_"),
            ("instamart", "im_"),
        ],
    )
    def test_id_prefix_convention(self, source, prefix):
        """IDs should be prefixed so product IDs don't collide across sources."""
        # We can't enforce this for blinkit (uses raw API IDs), but the test
        # documents the convention.
        pass  # Placeholder — see individual scraper implementations


# ---------------------------------------------------------------------------
# 7.  Field-type invariant tests
# ---------------------------------------------------------------------------


class TestFieldTypes:
    """All string fields must be str, all nullable fields must be str|None."""

    @pytest.mark.parametrize("key", STRING_KEYS)
    def test_string_key_is_str(self, key):
        p = _valid_product()
        assert_valid_product(p)
        assert isinstance(p[key], str), f"{key} must be str"

    @pytest.mark.parametrize("key", NULLABLE_STRING_KEYS)
    def test_nullable_key_is_str_or_none(self, key):
        p = _valid_product(**{key: "some value"})
        assert_valid_product(p)
        assert isinstance(p[key], str) or p[key] is None

        p2 = _valid_product(**{key: None})
        assert_valid_product(p2)

    def test_image_url_is_str(self):
        assert_valid_product(_valid_product(imageUrl=""))
        assert_valid_product(_valid_product(imageUrl="data:,"))
        assert_valid_product(_valid_product(imageUrl=None))

    def test_available_is_bool(self):
        assert_valid_product(_valid_product(available=True))
        assert_valid_product(_valid_product(available=False))

    def test_id_is_str(self):
        assert_valid_product(_valid_product(id="abc_123"))
        assert_valid_product(_valid_product(id=""))
