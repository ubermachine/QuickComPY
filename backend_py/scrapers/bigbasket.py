import urllib.parse
import asyncio
import re
import zendriver as zd

LOCATION_COORDS = {
    'delhi': '110001', 'new delhi': '110001', 'mumbai': '400001',
    'bengaluru': '560001', 'bangalore': '560001', 'hyderabad': '500001',
    'pune': '411001', 'kolkata': '700001', 'chennai': '600001',
    'ahmedabad': '380001', 'gurgaon': '122001', 'gurugram': '122001',
    'noida': '201301', '201306': '201306', '110001': '110001',
    '400001': '400001', '560001': '560001', '201301': '201301',
}

def resolve_pincode(location):
    if not location:
        return '201306'
    key = str(location).strip().lower()
    if key in LOCATION_COORDS:
        return LOCATION_COORDS[key]
    if re.match(r'^\d{6}$', key):
        return key
    for k, v in LOCATION_COORDS.items():
        if k in key or key in k:
            return v
    return '201306'

async def set_location(page, location):
    """Set location via CDP cookies (no UI interaction needed for BB)"""
    pincode = resolve_pincode(location)
    print(f"[Bigbasket] Setting location to pincode {pincode}")
    try:
        domain = '.bigbasket.com'
        await page.send(zd.cdp.network.set_cookie(name='bb_location', value=pincode, domain=domain, path='/'))
        await page.send(zd.cdp.network.set_cookie(name='bb_city', value='Noida', domain=domain, path='/'))
        await page.send(zd.cdp.network.set_cookie(name='bb_state', value='Uttar Pradesh', domain=domain, path='/'))
        await page.send(zd.cdp.network.set_cookie(name='bb_pincode', value=pincode, domain=domain, path='/'))
        await page.send(zd.cdp.network.set_cookie(name='bb_lat', value='28.5147', domain=domain, path='/'))
        await page.send(zd.cdp.network.set_cookie(name='bb_lon', value='77.4855', domain=domain, path='/'))
        try:
            await page.get("https://www.bigbasket.com/")
            await asyncio.sleep(1)
            await page.evaluate(f"""
                try {{ localStorage.setItem('bb_pincode', '{pincode}'); }} catch(e){{}}
                try {{ localStorage.setItem('bb_location', '{pincode}'); }} catch(e){{}}
            """)
        except Exception:
            pass
        print(f"[Bigbasket] Location cookies injected: {pincode}")
        return True
    except Exception as e:
        print(f"[Bigbasket] Location set error: {e}")
    return False

async def search(page, search_term):
    encoded = urllib.parse.quote(search_term)
    print(f"[Bigbasket] Searching for: {search_term}")

    collected_products = []
    resolved = {"done": False}
    target_requests = set()

    async def handle_response(event: zd.cdp.network.ResponseReceived):
        if resolved["done"]: return
        if "listing-svc/v2/products" in event.response.url and event.response.mime_type == "application/json":
            target_requests.add(event.request_id)

    async def handle_loading_finished(event: zd.cdp.network.LoadingFinished):
        if resolved["done"]: return
        if event.request_id not in target_requests: return
        
        try:
            body_info = await page.send(zd.cdp.network.get_response_body(request_id=event.request_id))
            if body_info:
                import json
                json_data = json.loads(body_info[0])
                tabs = json_data.get("tabs", [])
                if tabs:
                    product_info = tabs[0].get("product_info", {})
                    products = product_info.get("products", [])
                    
                    for p in products:
                        try:
                            pid = str(p.get("id", ""))
                            name = p.get("desc", "Unknown")
                            brand = p.get("brand", {}).get("name", "")
                            if brand and brand.lower() not in name.lower():
                                name = f"{brand} {name}"
                                
                            pricing = p.get("pricing", {})
                            discount_info = pricing.get("discount", {})
                            prim_price = discount_info.get("prim_price", {})
                            
                            sp = prim_price.get("sp")
                            mrp = discount_info.get("mrp")
                            
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
                                    
                            quantity = p.get("w", "") or p.get("weight", "") or "1 item"
                            
                            images = p.get("images", [])
                            image_url = ""
                            if images and isinstance(images, list):
                                image_url = images[0].get("m", "") or images[0].get("s", "")
                            
                            # Bigbasket standard delivery is usually listed as "Standard Delivery" or derived
                            delivery_time = "Standard Delivery"
                            
                            available = True # If it's in the search results, it's usually available unless marked
                            
                            collected_products.append({
                                "id": f"bb_{pid}",
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
                        except Exception as e:
                            print(f"[Bigbasket] Extractor loop error: {e}")
                    
                    if collected_products:
                        resolved["done"] = True
        except Exception as e:
            pass

    page.add_handler(zd.cdp.network.ResponseReceived, handle_response)
    page.add_handler(zd.cdp.network.LoadingFinished, handle_loading_finished)

    try:
        await page.send(zd.cdp.network.enable())
        await page.get(f"https://www.bigbasket.com/ps/?q={encoded}")
    except Exception:
        pass

    # Wait for API to fire
    for _ in range(150): # 15 seconds max
        if resolved["done"]: break
        await asyncio.sleep(0.1)

    page.remove_handlers(zd.cdp.network.ResponseReceived)
    page.remove_handlers(zd.cdp.network.LoadingFinished)

    return collected_products[:8]
