import urllib.parse
import asyncio
import time
import zendriver as zd

# Module-level pincode store set by set_location(), read by search()
_pincode = None
_lat = None
_lon = None

LOCATION_COORDS = {
    'delhi': { 'lat': 28.6327426, 'lon': 77.2195969 },
    'new delhi': { 'lat': 28.6327426, 'lon': 77.2195969 },
    'mumbai': { 'lat': 19.0760, 'lon': 72.8777 },
    'bengaluru': { 'lat': 12.9716, 'lon': 77.5946 },
    'bangalore': { 'lat': 12.9716, 'lon': 77.5946 },
    'hyderabad': { 'lat': 17.3850, 'lon': 78.4867 },
    'pune': { 'lat': 18.5204, 'lon': 73.8567 },
    'kolkata': { 'lat': 22.5726, 'lon': 88.3639 },
    'chennai': { 'lat': 13.0827, 'lon': 80.2707 },
    'ahmedabad': { 'lat': 23.0225, 'lon': 72.5714 },
    'gurgaon': { 'lat': 28.4595, 'lon': 77.0266 },
    'gurugram': { 'lat': 28.4595, 'lon': 77.0266 },
    'noida': { 'lat': 28.5821195, 'lon': 77.3266991 },
    '201306': { 'lat': 28.5821195, 'lon': 77.3266991 }, # Noida Sector 45 (fully serviceable in Zepto)
    '201301': { 'lat': 28.5821195, 'lon': 77.3266991 },
    '110001': { 'lat': 28.6327426, 'lon': 77.2195969 },
    '400001': { 'lat': 19.0760, 'lon': 72.8777 },
    '560001': { 'lat': 12.9716, 'lon': 77.5946 },
}

def resolve_coords(location):
    if not location:
        return LOCATION_COORDS['201301']
    key = str(location).strip().lower()
    if key in LOCATION_COORDS:
        return LOCATION_COORDS[key]
    for k, v in LOCATION_COORDS.items():
        if k in key or key in k:
            return v
    return LOCATION_COORDS['201301']

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

async def inject_location_cookies(page, pincode, lat, lon):
    try:
        await page.send(zd.cdp.network.delete_cookies(name='serviceability', domain='.zepto.com'))
        await page.send(zd.cdp.network.delete_cookies(name='serviceability', domain='www.zepto.com'))
        await page.send(zd.cdp.network.delete_cookies(name='serviceability', domain='zepto.com'))
    except Exception:
        pass
        
    domain = ".zepto.com"
    user_pos = f'{{"latitude":{lat},"longitude":{lon}}}'
    await page.send(zd.cdp.network.set_cookie(name='latitude', value=lat, domain=domain, path='/', secure=True))
    await page.send(zd.cdp.network.set_cookie(name='longitude', value=lon, domain=domain, path='/', secure=True))
    await page.send(zd.cdp.network.set_cookie(name='user_position', value=user_pos, domain=domain, path='/', secure=True))
    await page.send(zd.cdp.network.set_cookie(name='location', value=pincode, domain=domain, path='/', secure=True))
    
    domain2 = "www.zepto.com"
    await page.send(zd.cdp.network.set_cookie(name='latitude', value=lat, domain=domain2, path='/', secure=True))
    await page.send(zd.cdp.network.set_cookie(name='longitude', value=lon, domain=domain2, path='/', secure=True))
    await page.send(zd.cdp.network.set_cookie(name='user_position', value=user_pos, domain=domain2, path='/', secure=True))
    await page.send(zd.cdp.network.set_cookie(name='location', value=pincode, domain=domain2, path='/', secure=True))

async def set_location(page, location):
    """Set location via direct CDP cookies injection to bypass fragile UI"""
    global _pincode, _lat, _lon
    print(f"[Zepto] Setting location directly using cookies for {location}")
    coords = resolve_coords(location)
    pincode = str(location).strip()[:6] if location else '201301'
    
    _pincode = pincode
    _lat = str(coords['lat'])
    _lon = str(coords['lon'])
    
    try:
        # Establish domain session first
        await page.get("https://www.zepto.com/")
        await asyncio.sleep(1.5)
        
        # Inject coordinates and location cookies via CDP
        await inject_location_cookies(page, _pincode, _lat, _lon)
        
        # Reload so Zepto's server evaluates the new location cookies and sets serviceability cookie
        await page.get("https://www.zepto.com/")
        await asyncio.sleep(2)
        
        # Check serviceability and fall back if not serviceable
        cookies = await page.send(zd.cdp.network.get_cookies())
        serviceable = True
        for c in cookies:
            if c.name == 'serviceability':
                val = urllib.parse.unquote(c.value).lower().replace(" ", "")
                if '"serviceable":false' in val:
                    serviceable = False
                    break
                
        if not serviceable:
            print(f"[Zepto] Location {location} is not serviceable from this IP. Falling back to Noida 201301.")
            _pincode = '201301'
            _lat = '28.5821195'
            _lon = '77.3266991'
            await inject_location_cookies(page, _pincode, _lat, _lon)
            
            # Reload again so server evaluates the fallback location
            await page.get("https://www.zepto.com/")
            await asyncio.sleep(2)
            
        print(f"[Zepto] Location injected: pincode={_pincode}, lat={_lat}, lon={_lon}")
        return True
    except Exception as e:
        print(f"[Zepto] Location injection error: {e}")
    return False

async def search(page, search_term):
    global _pincode, _lat, _lon
    encoded = urllib.parse.quote(search_term)
    print(f"[Zepto] Searching for: {search_term}")
    
    pincode = _pincode or '201301'
    lat = _lat or '28.5821195'
    lon = _lon or '77.3266991'
    
    collected_products = []
    resolved = {"done": False}

    target_requests = set()

    async def handle_response(event: zd.cdp.network.ResponseReceived):
        if resolved["done"]: return
        if "api/v3/search" not in event.response.url or "filters" in event.response.url: return
        print(f"[Zepto DEBUG] Intercepted URL (response headers): {event.response.url}")
        target_requests.add(event.request_id)

    async def handle_loading_finished(event: zd.cdp.network.LoadingFinished):
        if resolved["done"]: return
        if event.request_id not in target_requests: return
        
        print(f"[Zepto DEBUG] Loading finished for request: {event.request_id}")
        try:
            body_info = await page.send(zd.cdp.network.get_response_body(request_id=event.request_id))
            if body_info:
                import json
                json_data = json.loads(body_info[0])
                if json_data and "layout" in json_data:
                    for widget in json_data.get("layout", []):
                        if widget.get("widgetId") == "PRODUCT_GRID":
                            items = widget.get("data", {}).get("resolver", {}).get("data", {}).get("items", [])
                            collected_products.extend(items)
                    
                    if collected_products:
                        print(f"[Zepto DEBUG] Found {len(collected_products)} products via API.")
                        resolved["done"] = True
                else:
                    print("[Zepto DEBUG] No layout in JSON.")
        except Exception as e:
            print(f"[Zepto DEBUG] Error in handle_loading_finished: {e}")
            # Remove failed request so we don't block; next matching response will be tried
            target_requests.discard(event.request_id)

    page.add_handler(zd.cdp.network.ResponseReceived, handle_response)
    page.add_handler(zd.cdp.network.LoadingFinished, handle_loading_finished)
    
    try:
        await page.send(zd.cdp.network.enable())
        # Establish domain session
        await page.get("https://www.zepto.com/")
        await asyncio.sleep(1.5)
        
        # Set location cookies WITHOUT deleting serviceability (already set by set_location)
        await page.send(zd.cdp.network.set_cookie(name='latitude', value=lat, domain='.zepto.com', path='/', secure=True))
        await page.send(zd.cdp.network.set_cookie(name='longitude', value=lon, domain='.zepto.com', path='/', secure=True))
        await page.send(zd.cdp.network.set_cookie(name='location', value=pincode, domain='.zepto.com', path='/', secure=True))
        
        # Navigate to search URL
        await page.get(f"https://www.zepto.com/search?query={encoded}")
    except Exception:
        pass

    # Wait for API to fire
    for _ in range(120): # 12 seconds max
        if resolved["done"]: break
        await asyncio.sleep(0.1)

    page.remove_handlers(zd.cdp.network.ResponseReceived)
    page.remove_handlers(zd.cdp.network.LoadingFinished)

    if not collected_products:
        print("[Zepto] No products found via API interception.")
        return []

    return extract_products(collected_products)

def extract_products(items):
    products = []
    for item in items:
        try:
            prod_resp = item.get("productResponse")
            if not prod_resp: continue
            
            product = prod_resp.get("product", {})
            variant = prod_resp.get("productVariant", {})
            
            pid = prod_resp.get("id") or product.get("id") or "Unknown"
            name = product.get("name", "Unknown")
            
            sp_paise = prod_resp.get("sellingPrice") or prod_resp.get("discountedSellingPrice") or 0
            mrp_paise = prod_resp.get("mrp") or sp_paise
            
            price = f"₹{sp_paise / 100:.2f}".rstrip('0').rstrip('.') if sp_paise else "N/A"
            orig_price = f"₹{mrp_paise / 100:.2f}".rstrip('0').rstrip('.') if mrp_paise else None
            
            savings = None
            discount = None
            if mrp_paise > sp_paise and sp_paise > 0:
                savings = f"₹{(mrp_paise - sp_paise) / 100:.2f}".rstrip('0').rstrip('.')
                discount = f"{int(round(((mrp_paise - sp_paise) / mrp_paise) * 100))}% OFF"
            
            quantity = variant.get("formattedPacksize", "1 item")
            
            images = variant.get("images", [])
            image_url = ""
            if images:
                image_path = images[0].get("path", "")
                if image_path:
                    image_url = f"https://cdn.zeptonow.com/{image_path}"
                    
            available = not prod_resp.get("outOfStock", False)
            
            products.append({
                "id": pid,
                "name": name,
                "price": price,
                "originalPrice": orig_price if orig_price != price else None,
                "savings": savings,
                "quantity": quantity,
                "deliveryTime": "10 mins",
                "discount": discount,
                "imageUrl": image_url,
                "available": available,
                "source": "zepto"
            })
        except Exception:
            pass
            
    return products[:8]