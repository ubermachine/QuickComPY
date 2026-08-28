import urllib.parse
import asyncio
import re
import zendriver as zd

from . import common

LOCATION_COORDS = {
    'delhi': '110001', 'new delhi': '110001', 'mumbai': '400001',
    'bengaluru': '560001', 'bangalore': '560001', 'hyderabad': '500001',
    'pune': '411001', 'kolkata': '700001', 'chennai': '600001',
    'ahmedabad': '380001', 'gurgaon': '122001', 'gurugram': '122001',
    'noida': '201301', '201306': '201306', '110001': '110001',
    '400001': '400001', '560001': '560001', '201301': '201301',
}

def resolve_pincode(location):
    if not location:
        return '201306'
    key = str(location).strip().lower()
    if key in LOCATION_COORDS:
        return LOCATION_COORDS[key]
    if re.match(r'^\d{6}$', key):
        return key
    for k, v in LOCATION_COORDS.items():
        if k in key or key in k:
            return v
    return '201306'

async def set_location(page, location):
    """Set location via CDP cookies (no UI interaction needed for BB)"""
    pincode = resolve_pincode(location)
    print(f"[Bigbasket] Setting location to pincode {pincode}")
    try:
        domain = '.bigbasket.com'
        await page.send(zd.cdp.network.set_cookie(name='bb_location', value=pincode, domain=domain, path='/'))
        await page.send(zd.cdp.network.set_cookie(name='bb_city', value='Noida', domain=domain, path='/'))
        await page.send(zd.cdp.network.set_cookie(name='bb_state', value='Uttar Pradesh', domain=domain, path='/'))
        await page.send(zd.cdp.network.set_cookie(name='bb_pincode', value=pincode, domain=domain, path='/'))
        await page.send(zd.cdp.network.set_cookie(name='bb_lat', value='28.5147', domain=domain, path='/'))
        await page.send(zd.cdp.network.set_cookie(name='bb_lon', value='77.4855', domain=domain, path='/'))
        try:
            await page.get("https://www.bigbasket.com/")
            await asyncio.sleep(1)
            await page.evaluate(f"""
                try {{ localStorage.setItem('bb_pincode', '{pincode}'); }} catch(e){{}}
                try {{ localStorage.setItem('bb_location', '{pincode}'); }} catch(e){{}}
            """)
        except Exception:
            pass
        print(f"[Bigbasket] Location cookies injected: {pincode}")
        return True
    except Exception as e:
        print(f"[Bigbasket] Location set error: {e}")
    return False


def extract_products(raw_products):
    products = []
    for p in raw_products:
        try:
            name = common.clean(p.get("desc"))
            if not name:
                continue
            brand = common.clean((p.get("brand") or {}).get("name"))
            if brand and brand.lower() not in name.lower():
                name = f"{brand} {name}"

            discount_info = (p.get("pricing") or {}).get("discount") or {}
            sp = (discount_info.get("prim_price") or {}).get("sp")
            price, orig_price, savings, discount = common.price_fields(sp, discount_info.get("mrp"))

            # BigBasket's own copy ("SAVE 15%") beats a computed percentage.
            offer = common.clean(discount_info.get("offer_entry_text") or discount_info.get("d_text"))
            if offer:
                discount = offer

            image_url = ""
            images = p.get("images")
            if isinstance(images, list) and images:
                image_url = images[0].get("m") or images[0].get("s") or ""

            # BigBasket runs both a slotted and an express ("BB Now") fleet; a
            # per-product ETA only exists on the express listings.
            eta = common.clean(p.get("bb_now_eta") or (p.get("delivery_info") or {}).get("eta"))

            # avail_status "001" is in stock; anything else is out of stock or
            # not serviceable at this pincode.
            availability = p.get("availability") or {}
            available = str(availability.get("avail_status", "001")) == "001"

            products.append({
                "id": f"bb_{p.get('id', name)}",
                "name": name,
                "price": price,
                "originalPrice": orig_price,
                "savings": savings,
                "quantity": common.clean(p.get("w") or p.get("weight")) or "1 item",
                "deliveryTime": eta or "Standard Delivery",
                "discount": discount,
                "imageUrl": image_url,
                "available": available,
                "source": "bigbasket",
            })
        except Exception as e:
            print(f"[Bigbasket] item parse error: {type(e).__name__}: {e}")
    return products


def _parse(payload):
    tabs = payload.get("tabs") or []
    if not tabs:
        return []
    product_info = tabs[0].get("product_info") or {}
    return extract_products(product_info.get("products") or [])


async def search(page, search_term):
    encoded = urllib.parse.quote(search_term)
    print(f"[Bigbasket] Searching for: {search_term}")

    async def attempt():
        return await common.intercept_json(
            page,
            tag="Bigbasket",
            match=lambda url: "listing-svc/v2/products" in url,
            parse=_parse,
            navigate=f"https://www.bigbasket.com/ps/?q={encoded}",
            timeout=18.0,
        )

    return await common.run_search(page, search_term, attempt, tag="Bigbasket")
