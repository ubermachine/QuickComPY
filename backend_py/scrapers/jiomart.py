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
    print(f"[JioMart] Attempting to set location to {location}")
    try:
        await page.get("https://www.jiomart.com/")
    except Exception as e:
        print(f"[JioMart] Error navigating: {e}")

    try:
        # JioMart location logic
        location_btn = await wait_for_selector(page, 'button[id="btn_pin_code"]', timeout=5)
        if location_btn:
            await location_btn.click()
            await asyncio.sleep(1)

            input_box = await wait_for_selector(page, 'input[id="rel_pincode"]', timeout=5)
            if input_box:
                await input_box.send_keys(location)

                apply_btn = await wait_for_selector(page, 'button[id="btn_pincode_apply"]', timeout=5)
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
        await page.get(f"https://www.jiomart.com/products?q={encoded}")

        try:
            await wait_for_selector(page, '.productCard__cardWrapper', timeout=15)
        except Exception:
            pass

        return await extract_from_html(page)
    except Exception as e:
        print(f"[JioMart] Search error: {e}")
        return []

async def extract_from_html(page):
    products = []
    try:
        cards = await page.select_all('.productCard__cardWrapper')
        for idx, card in enumerate(cards):
            try:
                name_el = await card.select('.productCard__productTitle')
                name = name_el.text if name_el and name_el.text else "Unknown"

                price_el = await card.select('.PriceContainer__currentPrice')
                price = price_el.text if price_el and price_el.text else "N/A"

                orig_el = await card.select('.PriceContainer__originalPrice')
                orig_price = orig_el.text if orig_el and orig_el.text else None

                qty_el = await card.select('.productCard__sizeSpan')
                if not qty_el:
                    qty_el = await card.select('.productCard__quantitySelector')
                quantity = qty_el.text if qty_el and qty_el.text else ""

                img_el = await card.select('.productCard__productImage')
                image_url = ""
                if img_el and hasattr(img_el, "attrs"):
                    image_url = img_el.attrs.get("src")
                    if not image_url:
                        image_url = img_el.attrs.get("data-src")

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
