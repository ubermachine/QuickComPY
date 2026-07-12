import urllib.parse
import asyncio

async def set_location(page, location):
    print(f"[JioMart] Attempting to set location to {location}")
    try:
        await page.goto("https://www.jiomart.com/", wait_until="domcontentloaded", timeout=30000)
    except Exception as e:
        print(f"[JioMart] Error navigating: {e}")

    try:
        # JioMart location logic
        location_btn = await page.wait_for_selector('button[id="btn_pin_code"]', timeout=5000)
        if location_btn:
            await location_btn.click()
            await asyncio.sleep(1)

            input_box = await page.wait_for_selector('input[id="rel_pincode"]', timeout=5000)
            if input_box:
                await input_box.fill(location)

                apply_btn = await page.wait_for_selector('button[id="btn_pincode_apply"]', timeout=5000)
                if apply_btn:
                    await apply_btn.click()
                    await asyncio.sleep(2)
                    return True
    except Exception as e:
        print(f"[JioMart] Location set error: {e}")
    return False

async def search(page, search_term):
    encoded = urllib.parse.quote(search_term)
    print(f"[JioMart] Searching for: {search_term}")

    try:
        await page.goto(f"https://www.jiomart.com/products?q={encoded}", wait_until="domcontentloaded", timeout=30000)

        try:
            await page.wait_for_selector('.productCard__cardWrapper', timeout=15000)
        except Exception:
            pass

        return await extract_from_html(page)
    except Exception as e:
        print(f"[JioMart] Search error: {e}")
        return []

async def extract_from_html(page):
    products = []
    try:
        cards = await page.query_selector_all('.productCard__cardWrapper')
        for idx, card in enumerate(cards):
            try:
                name_el = await card.query_selector('.productCard__productTitle')
                name = await name_el.inner_text() if name_el else "Unknown"

                price_el = await card.query_selector('.PriceContainer__currentPrice')
                price = await price_el.inner_text() if price_el else "N/A"

                orig_el = await card.query_selector('.PriceContainer__originalPrice')
                orig_price = await orig_el.inner_text() if orig_el else None

                qty_el = await card.query_selector('.productCard__sizeSpan')
                if not qty_el:
                    qty_el = await card.query_selector('.productCard__quantitySelector')
                quantity = await qty_el.inner_text() if qty_el else ""

                img_el = await card.query_selector('.productCard__productImage')
                image_url = ""
                if img_el:
                    image_url = await img_el.get_attribute("src")
                    if not image_url:
                        image_url = await img_el.get_attribute("data-src")

                savings = None
                discount = None

                if price and orig_price:
                    sp_str = ''.join(c for c in price if c.isdigit() or c == '.')
                    mrp_str = ''.join(c for c in orig_price if c.isdigit() or c == '.')
                    if sp_str and mrp_str:
                        sp_val = float(sp_str)
                        mrp_val = float(mrp_str)
                        if mrp_val > sp_val:
                            savings = f"₹{(mrp_val - sp_val):.2f}"
                            discount = f"{int(((mrp_val - sp_val) / mrp_val) * 100)}% OFF"

                products.append({
                    "id": f"jm_{idx}",
                    "name": name,
                    "price": price,
                    "originalPrice": orig_price,
                    "savings": savings,
                    "quantity": quantity,
                    "deliveryTime": "Standard Delivery",
                    "discount": discount,
                    "imageUrl": image_url,
                    "available": True,
                    "source": "jiomart"
                })
            except Exception:
                pass
    except Exception as e:
        print(f"[JioMart] Extraction error: {e}")

    return products
