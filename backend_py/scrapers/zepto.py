import urllib.parse
import asyncio
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
    print(f"[Zepto] Attempting to set location to {location}")
    try:
        await page.get("https://www.zeptonow.com/")
    except Exception as e:
        print(f"[Zepto] Error navigating: {e}")

    try:
        location_btn = await wait_for_selector(page, 'button[aria-label="Select Location"], div[class*="location-select"]', timeout=5)
        if location_btn:
            await location_btn.click()
            await asyncio.sleep(1)

            input_box = await wait_for_selector(page, 'input[placeholder*="Search a new address"], input[data-testid="location-search-input"]', timeout=5)
            if input_box:
                await input_box.send_keys(location)
                await asyncio.sleep(2)

                suggestions = await page.select_all('div[data-testid="location-search-result"]')
                if suggestions:
                    await suggestions[0].click()

                    try:
                        confirm_btn = await page.find("Confirm", best_match=True)
                        if confirm_btn:
                            await confirm_btn.click()
                    except Exception:
                        pass

                    await asyncio.sleep(2)
                    return True
    except Exception as e:
        print(f"[Zepto] Location set error: {e}")
    return False

async def search(page, search_term):
    encoded = urllib.parse.quote(search_term)
    print(f"[Zepto] Searching for: {search_term}")

    try:
        await page.get(f"https://www.zeptonow.com/search?q={encoded}")

        try:
            await wait_for_selector(page, 'a[data-testid="product-card"]', timeout=15)
        except Exception:
            pass

        return await extract_from_html(page)
    except Exception as e:
        print(f"[Zepto] Search error: {e}")
        return []

async def extract_from_html(page):
    products = []
    try:
        cards = await page.select_all('a[data-testid="product-card"]')
        for idx, card in enumerate(cards):
            try:
                name_el = await card.select('h5[data-testid="product-name"]')
                name = name_el.text if name_el and name_el.text else "Unknown"

                price_el = await card.select('h4[data-testid="product-card-price"]')
                price = price_el.text if price_el and price_el.text else "N/A"

                orig_el = await card.select('p[data-testid="product-card-mrp"]')
                orig_price = orig_el.text if orig_el and orig_el.text else None

                qty_el = await card.select('span[data-testid="product-card-quantity"]')
                quantity = qty_el.text if qty_el and qty_el.text else ""

                img_el = await card.select('img[data-testid="product-card-image"]')
                image_url = img_el.attrs.get("src") if img_el and hasattr(img_el, "attrs") else ""

                discount_el = await card.select('p[data-testid="product-card-discount-badge"]')
                discount = discount_el.text if discount_el and discount_el.text else None

                savings = None

                if price and orig_price:
                    sp_str = ''.join(c for c in price if c.isdigit() or c == '.')
                    mrp_str = ''.join(c for c in orig_price if c.isdigit() or c == '.')
                    if sp_str and mrp_str:
                        sp_val = float(sp_str)
                        mrp_val = float(mrp_str)
                        if mrp_val > sp_val:
                            savings = f"₹{(mrp_val - sp_val):.2f}"

                products.append({
                    "id": f"zp_{idx}",
                    "name": name,
                    "price": price,
                    "originalPrice": orig_price,
                    "savings": savings,
                    "quantity": quantity,
                    "deliveryTime": "10min",
                    "discount": discount,
                    "imageUrl": image_url,
                    "available": True,
                    "source": "zepto"
                })
            except Exception:
                pass
    except Exception as e:
        print(f"[Zepto] Extraction error: {e}")

    return products
