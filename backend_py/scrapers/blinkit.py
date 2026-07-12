import urllib.parse
import asyncio
import json
import time
import zendriver as zd

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
    print(f"[Blinkit] Attempting to set location to {location}")
    try:
        await page.get("https://blinkit.com/")
    except Exception as e:
        print(f"[Blinkit] Error navigating: {e}")

    try:
        # Wait for location button
        location_btn = await wait_for_selector(page, 'div[class*="LocationFacility"]', timeout=5)
        if location_btn:
            await location_btn.click()
            await asyncio.sleep(1)

            # Type location
            input_box = await wait_for_selector(page, 'input[name="select-locality"]', timeout=5)
            if input_box:
                await input_box.send_keys(location)
                await asyncio.sleep(2)

                # Click first suggestion
                suggestions = await page.select_all('div[class*="LocationSearchList__LocationListContainer"]')
                if suggestions:
                    await suggestions[0].click()
                    await asyncio.sleep(2)
                    return True
    except Exception as e:
        print(f"[Blinkit] Location set error: {e}")
    return False

async def search(page, search_term):
    encoded = urllib.parse.quote(search_term)
    print(f"[Blinkit] Searching for: {search_term}")

    collected_snippets = []
    resolved = {"done": False}

    async def handle_response(event: zd.cdp.network.ResponseReceived):
        if resolved["done"]: return
        if "blinkit.com/v1/layout/search" not in event.response.url: return

        try:
            body_info = await page.send(zd.cdp.network.get_response_body(request_id=event.request_id))
            if body_info:
                json_data = json.loads(body_info[0])
                if json_data and "response" in json_data and "snippets" in json_data["response"]:
                    snippets = json_data["response"]["snippets"]
                    collected_snippets.extend(snippets)
                    resolved["done"] = True
        except Exception:
            pass

    page.add_handler(zd.cdp.network.ResponseReceived, handle_response)

    try:
        await page.get(f"https://blinkit.com/s/?q={encoded}")
    except Exception:
        pass

    # Wait for API to fire
    for _ in range(80): # 8 seconds max
        if resolved["done"]: break
        await asyncio.sleep(0.1)

    page.remove_handlers(zd.cdp.network.ResponseReceived)

    if not collected_snippets:
        return []

    return extract_products(collected_snippets)

def extract_products(snippets):
    products = []
    for s in snippets:
        try:
            if s.get("type") != "product": continue
            data = s.get("data", {})
            if not data: continue

            name = data.get("name", "Unknown")
            pid = str(data.get("id", ""))
            quantity = data.get("unit", "")
            price = f"₹{data.get('price')}" if data.get("price") else "N/A"
            orig_price = f"₹{data.get('mrp')}" if data.get("mrp") and data.get("mrp") > data.get("price", 0) else None

            discount = data.get("discount_info", {}).get("text")
            savings = f"₹{data.get('mrp') - data.get('price')}" if orig_price else None

            image = data.get("image_url", "")
            available = not data.get("out_of_stock", False)
            delivery_time = data.get("eta_info", {}).get("text", "Standard Delivery")

            products.append({
                "id": pid,
                "name": name,
                "price": price,
                "originalPrice": orig_price,
                "savings": savings,
                "quantity": quantity,
                "deliveryTime": delivery_time,
                "discount": discount,
                "imageUrl": image,
                "available": available,
                "source": "blinkit"
            })
        except Exception:
            pass

    return products
