import urllib.parse
import asyncio
import re
import time

import zendriver as zd

from . import common

async def wait_for_selector(page, selector, timeout=10):
    start = time.time()
    while time.time() - start < timeout:
        try:
            elem = await page.select(selector)
            if elem:
                return elem
        except Exception:
            pass
        await asyncio.sleep(0.5)
    return None

async def set_location(page, location):
    print(f"[JioMart] Attempting to set location to {location}")
    try:
        await page.get("https://www.jiomart.com/")
        await asyncio.sleep(3)
        
        # Click "Select Location Manually" if the modal appears
        await page.evaluate("""
            const btns = Array.from(document.querySelectorAll('button'));
            const manualBtn = btns.find(b => b.textContent && b.textContent.includes('Select Location Manually'));
            if (manualBtn) { manualBtn.click(); }
        """)
        await asyncio.sleep(1)
        
        # Type pin code
        await page.evaluate(f"""
            const inputs = Array.from(document.querySelectorAll('input'));
            const pinInput = inputs.find(i => i.placeholder && i.placeholder.toLowerCase().includes('pin'));
            if (pinInput) {{
                pinInput.value = '{location}';
                pinInput.dispatchEvent(new Event('input', {{ bubbles: true }}));
                pinInput.dispatchEvent(new Event('change', {{ bubbles: true }}));
            }}
        """)
        await asyncio.sleep(1)
            
        # Click apply/submit
        await page.evaluate("""
            const btns2 = Array.from(document.querySelectorAll('button'));
            const applyBtn = btns2.find(b => b.textContent && b.textContent.includes('Apply'));
            if (applyBtn) { applyBtn.click(); }
        """)
        await asyncio.sleep(2)
        return True
    except Exception as e:
        print(f"[JioMart] Location set error: {e}")
        return False


# JioMart's search payload carries no pack-size field; the size is tacked onto
# the end of the product name ("Amul Taaza Toned Milk 500 ml").
_SIZE_RE = re.compile(
    r"(\d+(?:\.\d+)?\s?(?:g|gm|gms|kg|ml|l|ltr|litre|pcs|pc|pack|units?)\b)\s*$",
    re.I,
)


def _quantity(item, name):
    for key in ("weight", "pack_size", "size"):
        value = common.clean(item.get(key))
        if value:
            return value
    for attr_key in ("attributes", "custom_json"):
        attrs = item.get(attr_key)
        if isinstance(attrs, dict):
            value = common.clean(attrs.get("net_quantity") or attrs.get("pack_size"))
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
