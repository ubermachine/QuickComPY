import urllib.parse
import asyncio
import json
import time
import zendriver as zd

LOCATION_COORDS = {
  'delhi': { 'lat': 28.6139, 'lon': 77.2090 },
  'new delhi': { 'lat': 28.6139, 'lon': 77.2090 },
  'connaught place': { 'lat': 28.6315, 'lon': 77.2167 },
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
  'noida': { 'lat': 28.5355, 'lon': 77.3910 },
  'jaipur': { 'lat': 26.9124, 'lon': 75.7873 },
  '201306': { 'lat': 28.5147, 'lon': 77.4855 },
  'supertech ecovillage 1': { 'lat': 28.5147, 'lon': 77.4855 },
  'supertech ecovillage-1': { 'lat': 28.5147, 'lon': 77.4855 },
  'supertech eco village 1': { 'lat': 28.5147, 'lon': 77.4855 },
  'supertech eco village-1': { 'lat': 28.5147, 'lon': 77.4855 },
}

def resolve_coords(location):
    if not location:
        return LOCATION_COORDS['201306']
    key = str(location).strip().lower()
    if key in LOCATION_COORDS:
        return LOCATION_COORDS[key]
    for k, v in LOCATION_COORDS.items():
        if k in key or key in k:
            return v
    return LOCATION_COORDS['201306']

async def set_location(page, location):
    print(f"[Blinkit] Attempting to set location to {location}")
    coords = resolve_coords(location)
    lat = coords['lat']
    lon = coords['lon']
    try:
        # Inject cookies using CDP Network.setCookie
        await page.send(zd.cdp.network.set_cookie(
            name='gr_1_lat', value=str(lat), domain='.blinkit.com', path='/'
        ))
        await page.send(zd.cdp.network.set_cookie(
            name='gr_1_lon', value=str(lon), domain='.blinkit.com', path='/'
        ))
        await page.send(zd.cdp.network.set_cookie(
            name='gr_1_locality', value=str(location), domain='.blinkit.com', path='/'
        ))
        print(f"[Blinkit] Cookies injected: lat={lat}, lon={lon}")

        # Best effort navigation to establish session on domain
        try:
            await page.get("https://blinkit.com/")
            await asyncio.sleep(1)
            # Inject localStorage keys
            location_obj = {
                "coords": {"lat": lat, "lon": lon},
                "locality": str(location),
                "city": "Noida",
                "display_address": {"title": str(location), "description": str(location)}
            }
            script = f"""
            try {{ localStorage.setItem('gr_1_lat', '{lat}'); }} catch(e) {{}}
            try {{ localStorage.setItem('gr_1_lon', '{lon}'); }} catch(e) {{}}
            try {{ localStorage.setItem('gr_1_locality', '{location}'); }} catch(e) {{}}
            try {{ localStorage.setItem('location', JSON.stringify({json.dumps(location_obj)})); }} catch(e) {{}}
            """
            await page.evaluate(script)
        except Exception as e:
            print(f"[Blinkit] localStorage inject warn: {e}")
            
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
        raw = s.get("data")
        if not raw:
            continue
        
        # Skip containers / headers / non-product widgets
        widget_type = s.get("widget_type", "")
        if (
            widget_type == 'image_text_vr_type_header' or
            not raw.get("name") or
            not raw.get("identity") or
            raw.get("identity", {}).get("id") in ['product_container', 'listing_container', 'recent_searches_pill_container']
        ):
            continue

        try:
            pid = raw.get("identity", {}).get("id", "Unknown")
            # Only process numeric product IDs (skip string container IDs)
            try:
                int(pid)
            except ValueError:
                continue

            name = raw.get("name", {}).get("text", "Unknown").strip()
            
            price = "N/A"
            if raw.get("normal_price") and raw.get("normal_price", {}).get("text"):
                price = raw.get("normal_price", {}).get("text")
            elif raw.get("price") is not None:
                price = f"₹{raw.get('price')}"

            orig_price = None
            if raw.get("mrp") and raw.get("mrp", {}).get("text"):
                orig_price = raw.get("mrp", {}).get("text")

            quantity = raw.get("variant", {}).get("text", "N/A")
            image = raw.get("image", {}).get("url", "")
            
            delivery_time = "Standard Delivery"
            if raw.get("eta_tag") and raw.get("eta_tag", {}).get("title", {}).get("text"):
                delivery_time = raw.get("eta_tag", {}).get("title", {}).get("text")

            discount = None
            if raw.get("offer_tag") and raw.get("offer_tag", {}).get("title", {}).get("text"):
                discount = raw.get("offer_tag", {}).get("title", {}).get("text").replace("\n", " ")

            available = True
            if "is_sold_out" in raw:
                available = not raw["is_sold_out"]
            elif "inventory" in raw:
                available = raw["inventory"] > 0

            savings = None
            if orig_price and price:
                try:
                    import re
                    pr_match = re.search(r'₹\s*(\d+(?:\.\d+)?)', price)
                    op_match = re.search(r'₹\s*(\d+(?:\.\d+)?)', orig_price)
                    if pr_match and op_match:
                        cur = float(pr_match.group(1))
                        orig = float(op_match.group(1))
                        if orig > cur:
                            savings = f"₹{int(orig - cur)}"
                except Exception:
                    pass

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
        except Exception as e:
            print(f"[Blinkit] Extract snippet error: {e}")
            pass

    return products
