import urllib.parse
import asyncio
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

async def search(page, search_term):
    encoded = urllib.parse.quote(search_term)
    print(f"[JioMart] Searching for: {search_term}")

    collected_products = []
    resolved = {"done": False}
    target_requests = set()

    async def handle_response(event: zd.cdp.network.ResponseReceived):
        if resolved["done"]: return
        if event.response.mime_type != "application/json": return
        # Only intercept the specific vertex search API endpoint
        if "ext/vertex/application/api" in event.response.url and "products" in event.response.url:
            target_requests.add(event.request_id)

    async def handle_loading_finished(event: zd.cdp.network.LoadingFinished):
        if resolved["done"]: return
        if event.request_id not in target_requests: return
        
        try:
            body_info = await page.send(zd.cdp.network.get_response_body(request_id=event.request_id))
            if body_info:
                import json
                json_data = json.loads(body_info[0])
                items = json_data.get("items", [])
                
                for item in items:
                    try:
                        pid = str(item.get("uid", ""))
                        name = item.get("name", "Unknown")
                        
                        price_obj = item.get("price", {})
                        sp = price_obj.get("effective", {}).get("min")
                        mrp = price_obj.get("marked", {}).get("min")
                        
                        price = f"₹{sp}" if sp else "N/A"
                        orig_price = f"₹{mrp}" if mrp and str(mrp) != str(sp) else None
                        
                        savings = None
                        discount = None
                        if sp and mrp:
                            try:
                                f_sp = float(sp)
                                f_mrp = float(mrp)
                                if f_mrp > f_sp:
                                    savings = f"₹{int(f_mrp - f_sp)}"
                                    discount = f"{int(((f_mrp - f_sp)/f_mrp)*100)}% OFF"
                            except Exception:
                                pass
                                
                        # JioMart doesn't always have an explicit weight field at the top level
                        quantity = "1 item"
                        
                        medias = item.get("medias", [])
                        image_url = medias[0].get("url", "") if medias else ""
                        
                        available = item.get("sellable", True)
                        
                        collected_products.append({
                            "id": f"jm_{pid}",
                            "name": name,
                            "price": price,
                            "originalPrice": orig_price,
                            "savings": savings,
                            "quantity": quantity,
                            "deliveryTime": "Standard Delivery",
                            "discount": discount,
                            "imageUrl": image_url,
                            "available": available,
                            "source": "jiomart"
                        })
                    except Exception as e:
                        print(f"[JioMart] Extractor loop error: {e}")
                
                if collected_products:
                    resolved["done"] = True
        except Exception as e:
            pass

    try:
        await page.send(zd.cdp.network.enable())
        # Establish session first BEFORE adding handlers to avoid capturing homepage noise
        if "jiomart.com" not in page.url:
            await page.get("https://www.jiomart.com/")
            await asyncio.sleep(2)
    except Exception:
        pass

    # Add handlers AFTER homepage load to avoid capturing irrelevant JSON
    page.add_handler(zd.cdp.network.ResponseReceived, handle_response)
    page.add_handler(zd.cdp.network.LoadingFinished, handle_loading_finished)

    try:
        await page.get(f"https://www.jiomart.com/products?q={encoded}")
    except Exception:
        pass

    # Wait for API to fire
    for _ in range(150): # 15 seconds max
        if resolved["done"]: break
        await asyncio.sleep(0.1)

    page.remove_handlers(zd.cdp.network.ResponseReceived)
    page.remove_handlers(zd.cdp.network.LoadingFinished)

    return collected_products[:8]
