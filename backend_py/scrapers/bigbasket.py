import urllib.parse
import asyncio
import json
import re

async def set_location(page, location):
    print(f"[Bigbasket] Attempting to set location to {location}")
    try:
        await page.goto("https://www.bigbasket.com/", wait_until="domcontentloaded", timeout=30000)
    except Exception as e:
        print(f"[Bigbasket] Error navigating: {e}")

    try:
        location_header = await page.wait_for_selector('button:has-text("Location"), span:has-text("Location")', timeout=5000)
        if location_header:
            await location_header.click()
            await asyncio.sleep(1)

            input_box = await page.wait_for_selector('input[placeholder*="Search for your city"]', timeout=5000)
            if input_box:
                await input_box.fill(location)
                await asyncio.sleep(2)

                suggestions = await page.query_selector_all('ul[class*="overflow-y-auto"] li')
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
        await page.goto(f"https://www.bigbasket.com/ps/?q={encoded}", wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(2)

        # We try to extract from __PRELOADED_STATE__ directly
        html = await page.content()

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
        cards = await page.query_selector_all('div[class*="SKUDeck___StyledDiv"]')
        for card in cards:
            try:
                name_el = await card.query_selector('h3[class*="block m-0"]')
                name = await name_el.inner_text() if name_el else "Unknown"

                price_el = await card.query_selector('span[class*="Pricing___StyledLabel"]')
                price = await price_el.inner_text() if price_el else "N/A"

                orig_el = await card.query_selector('span[class*="Pricing___StyledLabel2"]')
                orig_price = await orig_el.inner_text() if orig_el else None

                qty_el = await card.query_selector('span[class*="PackChanger___StyledLabel"]')
                quantity = await qty_el.inner_text() if qty_el else ""

                img_el = await card.query_selector('img')
                image_url = await img_el.get_attribute("src") if img_el else ""

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
