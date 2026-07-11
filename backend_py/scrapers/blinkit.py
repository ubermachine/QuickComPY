import urllib.parse
import asyncio
import json

async def set_location(page, location):
    print(f"[Blinkit] Attempting to set location to {location}")
    try:
        await page.goto("https://blinkit.com/", wait_until="domcontentloaded", timeout=30000)
    except Exception as e:
        print(f"[Blinkit] Error navigating: {e}")

    try:
        # Wait for location button
        location_btn = await page.wait_for_selector('div[class*="LocationFacility"]', timeout=5000)
        if location_btn:
            await location_btn.click()
            await asyncio.sleep(1)

            # Type location
            input_box = await page.wait_for_selector('input[name="select-locality"]', timeout=5000)
            if input_box:
                await input_box.fill(location)
                await asyncio.sleep(2)

                # Click first suggestion
                suggestions = await page.query_selector_all('div[class*="LocationSearchList__LocationListContainer"]')
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

    async def handle_response(response):
        if resolved["done"]: return
        if "blinkit.com/v1/layout/search" not in response.url: return

        try:
            content_type = response.headers.get("content-type", "")
            if "application/json" not in content_type: return

            json_data = await response.json()
            if json_data and "response" in json_data and "snippets" in json_data["response"]:
                snippets = json_data["response"]["snippets"]
                collected_snippets.extend(snippets)
                resolved["done"] = True
        except Exception:
            pass

    page.on("response", handle_response)

    try:
        await page.goto(f"https://blinkit.com/s/?q={encoded}", wait_until="domcontentloaded", timeout=30000)
    except Exception:
        pass

    # Wait for API to fire
    for _ in range(80): # 8 seconds max
        if resolved["done"]: break
        await asyncio.sleep(0.1)

    page.remove_listener("response", handle_response)

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
