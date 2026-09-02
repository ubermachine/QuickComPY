import urllib.parse
import asyncio
import json

import zendriver as zd

from . import common

# Pincode-to-coordinate mapping for location injection
PINCODE_COORDINATES = {
    '201306': {'lat': 28.5147, 'lng': 77.4855, 'address': 'Noida, Uttar Pradesh, India'},
    '201301': {'lat': 28.5355, 'lng': 77.3910, 'address': 'Noida, Uttar Pradesh, India'},
    '400001': {'lat': 19.0760, 'lng': 72.8777, 'address': 'Mumbai, Maharashtra, India'},
    '110001': {'lat': 28.6139, 'lng': 77.2090, 'address': 'New Delhi, Delhi, India'},
    '560001': {'lat': 12.9716, 'lng': 77.5946, 'address': 'Bengaluru, Karnataka, India'},
    '500001': {'lat': 17.3850, 'lng': 78.4867, 'address': 'Hyderabad, Telangana, India'},
    '600001': {'lat': 13.0827, 'lng': 80.2707, 'address': 'Chennai, Tamil Nadu, India'},
    '700001': {'lat': 22.5726, 'lng': 88.3639, 'address': 'Kolkata, West Bengal, India'},
    '411001': {'lat': 18.5204, 'lng': 73.8567, 'address': 'Pune, Maharashtra, India'},
    '380001': {'lat': 23.0225, 'lng': 72.5714, 'address': 'Ahmedabad, Gujarat, India'},
}

# City name fallback mapping
CITY_COORDINATES = {
    'noida': PINCODE_COORDINATES['201306'],
    'delhi': PINCODE_COORDINATES['110001'],
    'mumbai': PINCODE_COORDINATES['400001'],
    'bangalore': PINCODE_COORDINATES['560001'],
    'bengaluru': PINCODE_COORDINATES['560001'],
    'hyderabad': PINCODE_COORDINATES['500001'],
    'chennai': PINCODE_COORDINATES['600001'],
    'kolkata': PINCODE_COORDINATES['700001'],
    'pune': PINCODE_COORDINATES['411001'],
    'ahmedabad': PINCODE_COORDINATES['380001'],
}

# Swiggy CDN image base URL
SWIGGY_IMG_CDN = "https://instamart-media-assets.swiggy.com/swiggy/image/upload/fl_lossy,f_auto,q_auto,h_300/"


async def set_location(page, location):
    """Point the browser at the requested coordinates before Instamart loads.

    Caveat worth knowing: unlike the other four platforms, Swiggy does not bind
    its dark store from anything we can set directly. Its search request carries
    an empty ``storeId`` and an opaque ``matcher`` header the SPA derives from
    its own state, and it ignores the localStorage keys an earlier version of
    this function invented. What we can do honestly is override the browser's
    geolocation, set the cookie Swiggy's own picker writes, and let the app
    resolve whatever store it will. Results come back with real catalogue prices
    either way, but they are not guaranteed to be pincode-exact.
    """
    print(f"[Instamart] Setting location for {location}")
    location_key = location.lower().strip()

    # Try pincode first, then city name fallback
    coords = PINCODE_COORDINATES.get(location_key)
    if not coords:
        coords = CITY_COORDINATES.get(location_key, PINCODE_COORDINATES['560001'])

    try:
        # Answer the geolocation API with our coordinates rather than leaving
        # the page to guess from the exit IP.
        try:
            await page.send(zd.cdp.browser.grant_permissions(
                permissions=[zd.cdp.browser.PermissionType.GEOLOCATION],
                origin="https://www.swiggy.com",
            ))
        except Exception:
            pass
        try:
            await page.send(zd.cdp.emulation.set_geolocation_override(
                latitude=coords['lat'], longitude=coords['lng'], accuracy=50,
            ))
        except Exception as e:
            print(f"[Instamart] geolocation override unavailable: {type(e).__name__}")

        await page.get("https://www.swiggy.com/instamart")
        await asyncio.sleep(2)

        # The cookie Swiggy's address picker writes, in the shape it writes it
        # (URL-encoded JSON, not raw JSON).
        payload = {
            'lat': coords['lat'],
            'lng': coords['lng'],
            'address': coords['address'],
            'area': coords['address'].split(',')[0],
        }
        await page.send(zd.cdp.network.set_cookie(
            name='userLocation',
            value=urllib.parse.quote(json.dumps(payload)),
            domain='.swiggy.com',
            path='/',
        ))
        print(f"[Instamart] Location applied: lat={coords['lat']}, lng={coords['lng']}")
        return True
    except Exception as e:
        print(f"[Instamart] Location set error: {e}")
        return False

def _parse(payload):
    products = []
    cards = (payload.get("data") or {}).get("cards") or []
    for card_wrapper in cards:
        card = ((card_wrapper.get("card") or {}).get("card")) or {}
        # Products only ever live in grid widgets; the rest are banners.
        if "GridWidget" not in card.get("@type", ""):
            continue

        items = ((card.get("gridElements") or {}).get("infoWithStyle") or {}).get("items") or []
        for item in items:
            try:
                name = common.clean(item.get("displayName"))
                variations = item.get("variations") or []
                if not name or not variations:
                    continue
                var = variations[0]

                price_obj = var.get("price") or {}
                sp = (price_obj.get("offerPrice") or {}).get("units")
                mrp = (price_obj.get("mrp") or {}).get("units")
                price, orig_price, savings, discount = common.price_fields(sp, mrp)

                # Swiggy's own offer copy is better than a computed percentage,
                # but it is frequently an empty string rather than absent.
                offer = common.clean((price_obj.get("offerApplied") or {}).get("listingDescription"))
                if offer:
                    discount = offer

                image_ids = var.get("imageIds") or []
                image_url = f"{SWIGGY_IMG_CDN}{image_ids[0]}" if image_ids else ""

                products.append({
                    "id": f"im_{var.get('skuId') or name}",
                    "name": name,
                    "price": price,
                    "originalPrice": orig_price,
                    "savings": savings,
                    "quantity": common.clean(var.get("quantityDescription")) or "1 item",
                    "deliveryTime": "10-15 mins",
                    "discount": discount,
                    "imageUrl": image_url,
                    "available": bool(item.get("inStock", True)) and bool(item.get("isAvail", True)),
                    "source": "instamart",
                })
            except Exception as e:
                print(f"[Instamart] item parse error: {type(e).__name__}: {e}")
    return products


async def search(page, search_term):
    """Search Instamart via its internal /api/instamart/search JSON.

    Reading the API response sidesteps AWS WAF entirely: the browser negotiates
    the WAF token natively as it loads the page, and we just read the payload
    it gets back.
    """
    encoded = urllib.parse.quote(search_term)
    print(f"[Instamart] Searching for: {search_term}")

    async def attempt():
        # set_location already parks us on swiggy.com; only pay for the warmup
        # navigation when the WAF token has not been established yet.
        warmup = None if "swiggy.com" in (page.url or "") else "https://www.swiggy.com/instamart"
        return await common.intercept_json(
            page,
            tag="Instamart",
            # Pin to the product-search endpoint. A looser "api/instamart/search"
            # also matches suggestion/autocomplete calls, and latching onto one
            # of those makes the engine give up before the real grid arrives.
            match=lambda url: "api/instamart/search/v2" in url,
            parse=_parse,
            navigate=f"https://www.swiggy.com/instamart/search?query={encoded}",
            warmup=warmup,
            warmup_wait=2.0,
            timeout=15.0,
        )

    return await common.run_search(page, search_term, attempt, tag="Instamart")
