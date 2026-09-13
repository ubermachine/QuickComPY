import urllib.parse
import json
import re

import zendriver as zd

from . import common

# JioMart keeps the delivery location in two cookies plus a localStorage key.
# Setting them directly is both faster and more reliable than driving the
# location modal: that modal's field is a Google Places autocomplete whose
# suggestion list does not lay out in headless Chrome (its .pac-item reports a
# zero-size bounding box), so neither synthetic nor real clicks can pick a
# result. The previous implementation slept seven seconds through that flow and
# returned True regardless, leaving every user on JioMart's Mumbai default.
LOCATIONS = {
    '201306': ('NOIDA', 'UTTAR PRADESH', '28.5147', '77.4855'),
    '201301': ('NOIDA', 'UTTAR PRADESH', '28.5355', '77.3910'),
    '110001': ('NEW DELHI', 'DELHI', '28.6139', '77.2090'),
    '400001': ('MUMBAI', 'MAHARASHTRA', '19.0760', '72.8777'),
    '560001': ('BENGALURU', 'KARNATAKA', '12.9716', '77.5946'),
    '500001': ('HYDERABAD', 'TELANGANA', '17.3850', '78.4867'),
    '600001': ('CHENNAI', 'TAMIL NADU', '13.0827', '80.2707'),
    '700001': ('KOLKATA', 'WEST BENGAL', '22.5726', '88.3639'),
    '411001': ('PUNE', 'MAHARASHTRA', '18.5204', '73.8567'),
    '380001': ('AHMEDABAD', 'GUJARAT', '23.0225', '72.5714'),
    '122001': ('GURUGRAM', 'HARYANA', '28.4595', '77.0266'),
    '302001': ('JAIPUR', 'RAJASTHAN', '26.9124', '75.7873'),
}

CITY_PINCODES = {
    'noida': '201306', 'delhi': '110001', 'new delhi': '110001',
    'mumbai': '400001', 'bengaluru': '560001', 'bangalore': '560001',
    'hyderabad': '500001', 'chennai': '600001', 'kolkata': '700001',
    'pune': '411001', 'ahmedabad': '380001', 'gurgaon': '122001',
    'gurugram': '122001', 'jaipur': '302001',
}

DEFAULT_PINCODE = '201306'

# The header echoes the resolved location, which is how we confirm it took.
_LOCATION_TEXT_JS = (
    "(function(){var m=(document.body.innerText||'').match"
    "(/Location\\s*\\n?\\s*([A-Za-z ,0-9]+INDIA)/);return m?m[1]:''})()"
)


def resolve_pincode(location):
    if not location:
        return DEFAULT_PINCODE
    key = str(location).strip().lower()
    if re.fullmatch(r'\d{6}', key):
        return key if key in LOCATIONS else DEFAULT_PINCODE
    if key in CITY_PINCODES:
        return CITY_PINCODES[key]
    for name, pin in CITY_PINCODES.items():
        if name in key or key in name:
            return pin
    return DEFAULT_PINCODE


async def set_location(page, location):
    """Set JioMart's delivery pincode via its own location cookies.

    Returns True only once JioMart's header echoes the pincode back, so the
    per-platform badge in the UI reflects something real.
    """
    pincode = resolve_pincode(location)
    city, state, lat, lng = LOCATIONS[pincode]
    print(f"[JioMart] Setting location to {pincode} ({city})")

    details = {
        "country": "INDIA", "country_iso_code": "IN",
        "city": city, "pincode": pincode, "state": state,
    }

    try:
        await page.get("https://www.jiomart.com/")
        await common.wait_for(page, "document.body", timeout=15.0)

        for name, value in (
            ("app_location_details", json.dumps(details)),
            ("app_geolocation", json.dumps({"latitude": lat, "longitude": lng})),
        ):
            await page.send(zd.cdp.network.set_cookie(
                name=name, value=urllib.parse.quote(value),
                domain=".jiomart.com", path="/",
            ))

        # The SPA reads this on boot; the cookies alone leave it stale.
        await page.evaluate(
            "localStorage.setItem('pin', " + json.dumps(json.dumps(details)) + ")"
        )

        await page.get("https://www.jiomart.com/")
        applied = await common.wait_for(
            page, f"/{pincode}/.test({_LOCATION_TEXT_JS})", timeout=8.0
        )
        shown = await page.evaluate(_LOCATION_TEXT_JS)
        print(f"[JioMart] Location now: {shown or '(unknown)'}")
        return bool(applied)
    except Exception as e:
        print(f"[JioMart] Location set error: {type(e).__name__}: {e}")
        return False


# JioMart's search payload carries no pack-size field; the size is tacked onto
# the end of the product name ("Amul Taaza Toned Milk 500 ml").
_SIZE_RE = re.compile(
    r"(\d+(?:\.\d+)?\s?(?:g|gm|gms|kg|ml|l|ltr|litre|pcs|pc|pack|units?)\b)\s*$",
    re.I,
)


def _quantity(item, name):
    # The quick-commerce payload carries the pack size properly, as a `sizes`
    # list ("1 L"). Prefer it: parsing the title only works when the size
    # happens to sit at the end, which "... Milk 1 L (Pouch)" does not.
    sizes = item.get("sizes")
    if isinstance(sizes, list) and sizes:
        value = common.clean(sizes[0])
        if value:
            return value

    net = item.get("net_quantity")
    if isinstance(net, dict) and net.get("value"):
        unit = common.clean(net.get("unit")) or ""
        return common.clean(f"{net['value']} {unit}")
    if isinstance(net, str):
        value = common.clean(net)
        if value:
            return value

    for key in ("weight", "pack_size", "size"):
        value = common.clean(item.get(key))
        if value:
            return value

    m = _SIZE_RE.search(name or "")
    return common.clean(m.group(1)) if m else "1 item"


def extract_products(items):
    products = []
    for item in items:
        try:
            name = common.clean(item.get("name"))
            if not name:
                continue

            price_obj = item.get("price") or {}
            price, orig_price, savings, discount = common.price_fields(
                (price_obj.get("effective") or {}).get("min"),
                (price_obj.get("marked") or {}).get("min"),
            )

            medias = item.get("medias") or []
            image_url = medias[0].get("url", "") if medias else ""

            products.append({
                "id": f"jm_{item.get('uid', name)}",
                "name": name,
                "price": price,
                "originalPrice": orig_price,
                "savings": savings,
                "quantity": _quantity(item, name),
                "deliveryTime": "Standard Delivery",
                "discount": discount,
                "imageUrl": image_url,
                "available": bool(item.get("sellable", True)),
                "source": "jiomart",
            })
        except Exception as e:
            print(f"[JioMart] item parse error: {type(e).__name__}: {e}")
    return products


def _parse(payload):
    return extract_products(payload.get("items") or [])


async def search(page, search_term):
    encoded = urllib.parse.quote(search_term)
    print(f"[JioMart] Searching for: {search_term}")

    async def attempt():
        # A tab already sitting on the origin carries the session this
        # navigation exists to create. Under the pooled tabs in main.py that is
        # now rare, because release blanks the tab to about:blank -- what
        # actually skips the warmup is intercept_json's own per-origin cookie
        # check against the shared browser profile, which pooling does not
        # affect. Kept because it is still correct, and free when it does hit.
        warmup = None if "jiomart.com" in (page.url or "") else "https://www.jiomart.com/"
        return await common.intercept_json(
            page,
            tag="JioMart",
            match=lambda url: "ext/vertex/application/api" in url and "products" in url,
            parse=_parse,
            navigate=f"https://www.jiomart.com/products?q={encoded}",
            warmup=warmup,
            warmup_wait=2.0,
            timeout=18.0,
        )

    return await common.run_search(page, search_term, attempt, tag="JioMart")
