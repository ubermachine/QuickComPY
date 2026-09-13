import urllib.parse

import zendriver as zd

from . import common

# Module-level pincode store set by set_location(), read by search()
_pincode = None
_lat = None
_lon = None

LOCATION_COORDS = {
    'delhi': { 'lat': 28.6327426, 'lon': 77.2195969 },
    'new delhi': { 'lat': 28.6327426, 'lon': 77.2195969 },
    'mumbai': { 'lat': 19.0760, 'lon': 72.8777 },
    'bengaluru': { 'lat': 12.9716, 'lon': 77.5946 },
    'bangalore': { 'lat': 12.9716, 'lon': 77.5946 },
    'hyderabad': { 'lat': 17.3850, 'lon': 78.4867 },
    'pune': { 'lat': 18.5204, 'lon': 73.8567 },
    'kolkata': { 'lat': 22.5726, 'lon': 88.3639 },
    'chennai': { 'lat': 13.0827, 'lon': 80.2707 },
    'ahmedabad': { 'lat': 23.0225, 'lon': 72.5714 },
    'gurgaon': { 'lat': 28.4595, 'lon': 77.0266 },
    'gurugram': { 'lat': 28.4595, 'lon': 77.0266 },
    'noida': { 'lat': 28.5821195, 'lon': 77.3266991 },
    '201306': { 'lat': 28.5821195, 'lon': 77.3266991 }, # Noida Sector 45 (fully serviceable in Zepto)
    '201301': { 'lat': 28.5821195, 'lon': 77.3266991 },
    '110001': { 'lat': 28.6327426, 'lon': 77.2195969 },
    '400001': { 'lat': 19.0760, 'lon': 72.8777 },
    '560001': { 'lat': 12.9716, 'lon': 77.5946 },
}

def resolve_coords(location):
    if not location:
        return LOCATION_COORDS['201301']
    key = str(location).strip().lower()
    if key in LOCATION_COORDS:
        return LOCATION_COORDS[key]
    for k, v in LOCATION_COORDS.items():
        if k in key or key in k:
            return v
    return LOCATION_COORDS['201301']

async def inject_location_cookies(page, pincode, lat, lon):
    # Each domain gets its own guard: sharing one meant a failure on the first
    # silently skipped the other two, and set_location then waits on the
    # serviceability cookie reappearing to know the server has re-evaluated
    # the location -- a stale copy left behind would answer for the old one.
    for domain in ('.zepto.com', 'www.zepto.com', 'zepto.com'):
        try:
            await page.send(zd.cdp.network.delete_cookies(name='serviceability', domain=domain))
        except Exception:
            pass
        
    domain = ".zepto.com"
    user_pos = f'{{"latitude":{lat},"longitude":{lon}}}'
    await page.send(zd.cdp.network.set_cookie(name='latitude', value=lat, domain=domain, path='/', secure=True))
    await page.send(zd.cdp.network.set_cookie(name='longitude', value=lon, domain=domain, path='/', secure=True))
    await page.send(zd.cdp.network.set_cookie(name='user_position', value=user_pos, domain=domain, path='/', secure=True))
    await page.send(zd.cdp.network.set_cookie(name='location', value=pincode, domain=domain, path='/', secure=True))
    
    domain2 = "www.zepto.com"
    await page.send(zd.cdp.network.set_cookie(name='latitude', value=lat, domain=domain2, path='/', secure=True))
    await page.send(zd.cdp.network.set_cookie(name='longitude', value=lon, domain=domain2, path='/', secure=True))
    await page.send(zd.cdp.network.set_cookie(name='user_position', value=user_pos, domain=domain2, path='/', secure=True))
    await page.send(zd.cdp.network.set_cookie(name='location', value=pincode, domain=domain2, path='/', secure=True))

async def set_location(page, location):
    """Set location via direct CDP cookies injection to bypass fragile UI"""
    global _pincode, _lat, _lon
    print(f"[Zepto] Setting location directly using cookies for {location}")
    coords = resolve_coords(location)
    pincode = str(location).strip()[:6] if location else '201301'
    
    _pincode = pincode
    _lat = str(coords['lat'])
    _lon = str(coords['lon'])
    
    try:
        # Establish domain session first: the cookies below are injected by CDP
        # against the zepto.com domain, and Chrome only keeps them once that
        # origin is the one loaded in the tab.
        await page.get("https://www.zepto.com/")
        await common.wait_for(
            page,
            "location.hostname.indexOf('zepto.com') !== -1 && document.readyState !== 'loading'",
            timeout=1.5,
        )

        # Inject coordinates and location cookies via CDP
        await inject_location_cookies(page, _pincode, _lat, _lon)

        # Reload so Zepto's server evaluates the new location cookies and sets
        # the serviceability cookie. That cookie reappearing (it was deleted
        # just above) is precisely what the wait is for, so wait for the thing
        # itself rather than for a duration someone guessed it would take.
        await page.get("https://www.zepto.com/")
        cookie = await common.wait_for_cookie(page, 'serviceability', timeout=2.0)

        # Absent means Zepto never told us, which we read as serviceable --
        # exactly what the previous cookie scan concluded when it found none.
        serviceable = True
        if cookie:
            val = urllib.parse.unquote(cookie.value).lower().replace(" ", "")
            if '"serviceable":false' in val:
                serviceable = False

        if not serviceable:
            print(f"[Zepto] Location {location} is not serviceable from this IP. Falling back to Noida 201301.")
            _pincode = '201301'
            _lat = '28.5821195'
            _lon = '77.3266991'
            await inject_location_cookies(page, _pincode, _lat, _lon)

            # Reload again so server evaluates the fallback location, and let it
            # say so before handing the tab on.
            await page.get("https://www.zepto.com/")
            await common.wait_for_cookie(page, 'serviceability', timeout=2.0)

        print(f"[Zepto] Location injected: pincode={_pincode}, lat={_lat}, lon={_lon}")
        return True
    except Exception as e:
        print(f"[Zepto] Location injection error: {e}")
    return False


def extract_products(items):
    products = []
    for item in items:
        try:
            prod_resp = item.get("productResponse")
            if not prod_resp:
                continue

            product = prod_resp.get("product") or {}
            variant = prod_resp.get("productVariant") or {}

            name = common.clean(product.get("name"))
            if not name:
                continue

            # Zepto quotes money in paise. discountedSellingPrice is what is
            # actually charged when a promo is live, so it wins over sellingPrice.
            sp_paise = prod_resp.get("discountedSellingPrice") or prod_resp.get("sellingPrice") or 0
            mrp_paise = prod_resp.get("mrp") or 0
            price, orig_price, savings, discount = common.price_fields(
                sp_paise / 100 if sp_paise else None,
                mrp_paise / 100 if mrp_paise else None,
            )

            image_url = ""
            images = variant.get("images") or []
            if images:
                path = images[0].get("path", "")
                if path:
                    image_url = f"https://cdn.zeptonow.com/{path}"

            products.append({
                "id": f"zp_{prod_resp.get('id') or product.get('id') or name}",
                "name": name,
                "price": price,
                "originalPrice": orig_price,
                "savings": savings,
                "quantity": common.clean(variant.get("formattedPacksize")) or "1 item",
                "deliveryTime": "10 mins",
                "discount": discount,
                "imageUrl": image_url,
                "available": not prod_resp.get("outOfStock", False),
                "source": "zepto",
            })
        except Exception as e:
            print(f"[Zepto] item parse error: {type(e).__name__}: {e}")
    return products


def _parse(payload):
    items = []
    for widget in payload.get("layout") or []:
        if widget.get("widgetId") != "PRODUCT_GRID":
            continue
        resolver_data = ((widget.get("data") or {}).get("resolver") or {}).get("data") or {}
        items.extend(resolver_data.get("items") or [])
    return extract_products(items)


async def search(page, search_term):
    encoded = urllib.parse.quote(search_term)
    print(f"[Zepto] Searching for: {search_term}")

    pincode = _pincode or '201301'
    lat = _lat or '28.5821195'
    lon = _lon or '77.3266991'

    async def set_cookies():
        # These have to land after the origin exists, otherwise Chrome drops
        # them and Zepto answers for its default store instead of ours.
        for name, value in (("latitude", lat), ("longitude", lon), ("location", pincode)):
            await page.send(zd.cdp.network.set_cookie(
                name=name, value=str(value), domain='.zepto.com', path='/', secure=True
            ))

    async def attempt():
        return await common.intercept_json(
            page,
            tag="Zepto",
            match=lambda url: "api/v3/search" in url and "filters" not in url,
            parse=_parse,
            navigate=f"https://www.zepto.com/search?query={encoded}",
            # Same short-circuit as Instamart and JioMart, and with the same
            # caveat: every scrape starts on a fresh tab, so in practice it is
            # intercept_json's per-origin cookie check that skips the warmup.
            warmup=None if "zepto.com" in (page.url or "") else "https://www.zepto.com/",
            before_navigate=set_cookies,
            timeout=15.0,
        )

    return await common.run_search(page, search_term, attempt, tag="Zepto")
