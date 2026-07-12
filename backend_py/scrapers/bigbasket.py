import urllib.parse
import asyncio
import json
import re
import time

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
    print(f"[Bigbasket] Attempting to set location to {location}")
    try:
        await page.get("https://www.bigbasket.com/")
    except Exception as e:
        print(f"[Bigbasket] Error navigating: {e}")

    try:
        location_header = await page.find("Location", best_match=True)
        if location_header:
            await location_header.click()
            await asyncio.sleep(1)

            input_box = await wait_for_selector(page, 'input[placeholder*="Search for your city"]', timeout=5)
            if input_box:
                await input_box.send_keys(location)
                await asyncio.sleep(2)

                suggestions = await page.select_all('ul[class*="overflow-y-auto"] li')
                if suggestions:
                    await suggestions[0].click()
                    await asyncio.sleep(2)
                    return True
    except Exception as e:
        print(f"[Bigbasket] Location set error: {e}")
    return False

async def search(page, search_term):
    encoded = urllib.parse.quote(search_term)
    print(f"[Bigbasket] Searching for: {search_term}")

    try:
        await page.get(f"https://www.bigbasket.com/ps/?q={encoded}")
        await asyncio.sleep(2)

        # We try to extract from __PRELOADED_STATE__ directly
        html = await page.get_content()

        match = re.search(r'window\.__PRELOADED_STATE__\s*=\s*(\{.*?\});', html)
        if match:
            state = json.loads(match.group(1))
            return extract_products_from_state(state)

        # Fallback to direct HTML extraction if state is missing
        return await extract_from_html(page)

    except Exception as e:
        print(f"[Bigbasket] Search error: {e}")
        return []

def extract_products_from_state(state):
    products = []
    try:
        search_data = state.get("searchState", {}).get("searchResult", {})
        tabs = search_data.get("tabs", [])
        if not tabs: return products

        raw_products = tabs[0].get("product_info", {}).get("products", [])

        for idx, p in enumerate(raw_products):
            try:
                pid = str(p.get("id", f"bb_{idx}"))
                name = p.get("desc", "Unknown")
                quantity = p.get("w", "")

                price = "N/A"
                orig_price = None
                savings = None
                discount = None

                pricing = p.get("pricing", {}).get("discount", {})
                if pricing:
                    sp = pricing.get("prim_price", {}).get("sp")
                    mrp = pricing.get("mrp")

                    if sp: price = f"₹{sp}"
                    if mrp and sp and float(mrp) > float(sp):
                        orig_price = f"₹{mrp}"
                        savings = f"₹{float(mrp) - float(sp):.2f}"
                        discount = f"{int(((float(mrp) - float(sp)) / float(mrp)) * 100)}% OFF"

                images = p.get("images", [])
                image_url = images[0].get("s", "") if images else ""

                availability = p.get("availability", {})
                delivery_time = availability.get("short_eta", "Standard Delivery")
                available = availability.get("avail_status") == "001"

                products.append({
                    "id": pid,
                    "name": name,
                    "price": price,
                    "originalPrice": orig_price,
                    "savings": savings,
                    "quantity": quantity,
                    "deliveryTime": delivery_time,
                    "discount": discount,
                    "imageUrl": image_url,
                    "available": available,
                    "source": "bigbasket"
                })
            except Exception:
                pass

    except Exception as e:
        print(f"[Bigbasket] Extraction error: {e}")

    return products

async def extract_from_html(page):
    products = []
    try:
        cards = await page.select_all('div[class*="SKUDeck___StyledDiv"]')
        for card in cards:
            try:
                name_el = await card.select('h3[class*="block m-0"]')
                name = name_el.text if name_el and name_el.text else "Unknown"

                price_el = await card.select('span[class*="Pricing___StyledLabel"]')
                price = price_el.text if price_el and price_el.text else "N/A"

                orig_el = await card.select('span[class*="Pricing___StyledLabel2"]')
                orig_price = orig_el.text if orig_el and orig_el.text else None

                qty_el = await card.select('span[class*="PackChanger___StyledLabel"]')
                quantity = qty_el.text if qty_el and qty_el.text else ""

                img_el = await card.select('img')
                image_url = img_el.attrs.get("src") if img_el and hasattr(img_el, "attrs") else ""

                products.append({
                    "id": name,
                    "name": name,
                    "price": price,
                    "originalPrice": orig_price,
                    "savings": None,
                    "quantity": quantity,
                    "deliveryTime": "Standard Delivery",
                    "discount": None,
                    "imageUrl": image_url,
                    "available": True,
                    "source": "bigbasket"
                })
            except Exception:
                pass
    except Exception:
        pass
    return products
