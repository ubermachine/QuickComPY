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
        # Find location button by iterating over buttons
        buttons = await page.select_all("button")
        location_btn = None
        for btn in buttons:
            try:
                txt = btn.text
                if txt and any(x in txt for x in ["Select Location", "Deliver to", "Delivery in", "Get it in"]):
                    location_btn = btn
                    break
            except Exception:
                pass
        
        if location_btn:
            await location_btn.click()
            await asyncio.sleep(1.5)

            # Find input box by looking at placeholders
            inputs = await page.select_all("input")
            input_box = None
            for inp in inputs:
                try:
                    ph = inp.attrs.get("placeholder", "")
                    if any(x in ph for x in ["Search for area", "Search for your city", "Search for street", "Search for address"]):
                        input_box = inp
                        break
                except Exception:
                    pass

            if input_box:
                await input_box.send_keys(location)
                await asyncio.sleep(2.5)

                suggestions = await page.select_all('ul li, li')
                target_suggestion = None
                for sug in suggestions:
                    try:
                        sug_txt = sug.text
                        if sug_txt and any(c.isdigit() for c in sug_txt):
                            target_suggestion = sug
                            break
                    except Exception:
                        pass
                
                if not target_suggestion and suggestions:
                    target_suggestion = suggestions[0]

                if target_suggestion:
                    await target_suggestion.click()
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
        await asyncio.sleep(3)

        # We try to extract from __PRELOADED_STATE__ directly
        html = await page.get_content()

        match = re.search(r'window\.__PRELOADED_STATE__\s*=\s*(\{.*?\});', html)
        if match:
            try:
                state = json.loads(match.group(1))
                prods = extract_products_from_state(state)
                if prods:
                    return prods
            except Exception:
                pass

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
    try:
        return await page.evaluate("""
        (() => {
            const products = [];
            const cards = document.querySelectorAll('div[class*="SKUDeck___StyledDiv"], [class*="skudeck"], div[class*="SkuDeck___StyledDiv"]');
            cards.forEach((card, idx) => {
                try {
                    const nameEl = card.querySelector('h3[class*="block m-0"], h3');
                    const name = nameEl ? nameEl.textContent.trim() : 'Unknown';
                    
                    const priceEl = card.querySelector('span[class*="Pricing___StyledLabel"], [class*="pricing"], span[class*="Pricing___StyledLabel2"]');
                    const price = priceEl ? priceEl.textContent.trim() : 'N/A';
                    
                    const origEl = card.querySelector('span[class*="Pricing___StyledLabel2"], [class*="mrp"], span[class*="Pricing___StyledLabel3"]');
                    const origPrice = (origEl && origEl !== priceEl) ? origEl.textContent.trim() : null;
                    
                    const qtyEl = card.querySelector('span[class*="PackChanger___StyledLabel"], [class*="pack-changer"]');
                    const quantity = qtyEl ? qtyEl.textContent.trim() : '';
                    
                    const imgEl = card.querySelector('img');
                    const imageUrl = imgEl ? imgEl.src : '';
                    
                    let savings = null;
                    let discount = null;
                    if (price && origPrice) {
                        const spVal = parseFloat(price.replace(/[^0-9.]/g, ''));
                        const mrpVal = parseFloat(origPrice.replace(/[^0-9.]/g, ''));
                        if (mrpVal > spVal) {
                            savings = '₹' + (mrpVal - spVal).toFixed(2);
                            discount = Math.round(((mrpVal - spVal) / mrpVal) * 100) + '% OFF';
                        }
                    }
                    
                    products.push({
                        id: 'bb_' + idx,
                        name,
                        price,
                        originalPrice: origPrice,
                        savings,
                        quantity,
                        deliveryTime: "Standard Delivery",
                        discount,
                        imageUrl,
                        available: true,
                        source: 'bigbasket'
                    });
                } catch(e) {}
            });
            return products;
        })()
        """)
    except Exception as e:
        print(f"[Bigbasket] HTML extraction error: {e}")
        return []
