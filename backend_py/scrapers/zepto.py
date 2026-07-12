import urllib.parse
import asyncio

async def set_location(page, location):
    print(f"[Zepto] Attempting to set location to {location}")
    try:
        await page.goto("https://www.zeptonow.com/", wait_until="domcontentloaded", timeout=30000)
    except Exception as e:
        print(f"[Zepto] Error navigating: {e}")

    try:
        location_btn = await page.wait_for_selector('button[aria-label="Select Location"], div[class*="location-select"]', timeout=5000)
        if location_btn:
            await location_btn.click()
            await asyncio.sleep(1)

            input_box = await page.wait_for_selector('input[placeholder*="Search a new address"], input[data-testid="location-search-input"]', timeout=5000)
            if input_box:
                await input_box.fill(location)
                await asyncio.sleep(2)

                suggestions = await page.query_selector_all('div[data-testid="location-search-result"]')
                if suggestions:
                    await suggestions[0].click()

                    confirm_btn = await page.wait_for_selector('button:has-text("Confirm")', timeout=3000)
                    if confirm_btn:
                        await confirm_btn.click()

                    await asyncio.sleep(2)
                    return True
    except Exception as e:
        print(f"[Zepto] Location set error: {e}")
    return False

async def search(page, search_term):
    encoded = urllib.parse.quote(search_term)
    print(f"[Zepto] Searching for: {search_term}")

    try:
        await page.goto(f"https://www.zeptonow.com/search?q={encoded}", wait_until="domcontentloaded", timeout=30000)

        try:
            await page.wait_for_selector('a[data-testid="product-card"]', timeout=15000)
        except Exception:
            pass

        return await extract_from_html(page)
    except Exception as e:
        print(f"[Zepto] Search error: {e}")
        return []

async def extract_from_html(page):
    products = []
    try:
        cards = await page.query_selector_all('a[data-testid="product-card"]')
        for idx, card in enumerate(cards):
            try:
                name_el = await card.query_selector('h5[data-testid="product-name"]')
                name = await name_el.inner_text() if name_el else "Unknown"

                price_el = await card.query_selector('h4[data-testid="product-card-price"]')
                price = await price_el.inner_text() if price_el else "N/A"

                orig_el = await card.query_selector('p[data-testid="product-card-mrp"]')
                orig_price = await orig_el.inner_text() if orig_el else None

                qty_el = await card.query_selector('span[data-testid="product-card-quantity"]')
                quantity = await qty_el.inner_text() if qty_el else ""

                img_el = await card.query_selector('img[data-testid="product-card-image"]')
                image_url = await img_el.get_attribute("src") if img_el else ""

                discount_el = await card.query_selector('p[data-testid="product-card-discount-badge"]')
                discount = await discount_el.inner_text() if discount_el else None

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
