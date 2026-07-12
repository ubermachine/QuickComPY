import urllib.parse
import asyncio
import json
import time
import zendriver as zd

CITY_COORDINATES = {
  'delhi': { 'lat': 28.6139, 'lng': 77.2090, 'address': 'New Delhi, Delhi, India' },
  'mumbai': { 'lat': 19.0760, 'lng': 72.8777, 'address': 'Mumbai, Maharashtra, India' },
  'bangalore': { 'lat': 12.9716, 'lng': 77.5946, 'address': 'Bengaluru, Karnataka, India' },
  'bengaluru': { 'lat': 12.9716, 'lng': 77.5946, 'address': 'Bengaluru, Karnataka, India' },
  'hyderabad': { 'lat': 17.3850, 'lng': 78.4867, 'address': 'Hyderabad, Telangana, India' },
  'chennai': { 'lat': 13.0827, 'lng': 80.2707, 'address': 'Chennai, Tamil Nadu, India' },
  'kolkata': { 'lat': 22.5726, 'lng': 88.3639, 'address': 'Kolkata, West Bengal, India' },
  'pune': { 'lat': 18.5204, 'lng': 73.8567, 'address': 'Pune, Maharashtra, India' },
  'ahmedabad': { 'lat': 23.0225, 'lng': 72.5714, 'address': 'Ahmedabad, Gujarat, India' },
}

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
    print(f"[Instamart] Attempting to set location to {location}")

    city_key = location.lower().strip()
    coords = CITY_COORDINATES.get(city_key, CITY_COORDINATES['bangalore'])

    try:
        if "swiggy.com/instamart" not in page.url:
            await page.get("https://www.swiggy.com/instamart")

        # Inject location via JS
        script = f"""
        (() => {{
            const lat = {coords['lat']};
            const lng = {coords['lng']};
            const address = "{coords['address']}";
            const locationData = {{
                lat: lat,
                lng: lng,
                address: address,
                area: address.split(',')[0],
                city: address.split(',')[1] ? address.split(',')[1].trim() : '',
                areaId: '',
                latlng: `${{lat}},${{lng}}`
            }};
            try {{ localStorage.setItem('userLocation', JSON.stringify(locationData)); }} catch(e) {{}}
            try {{ localStorage.setItem('swiggy_location', JSON.stringify(locationData)); }} catch(e) {{}}
            try {{ localStorage.setItem('IM_location', JSON.stringify(locationData)); }} catch(e) {{}}
            try {{ sessionStorage.setItem('userLocation', JSON.stringify(locationData)); }} catch(e) {{}}
        }})()
        """
        await page.evaluate(script)

        await page.send(zd.cdp.network.set_cookie(
            name='userLocation',
            value=json.dumps({'lat': coords['lat'], 'lng': coords['lng']}),
            domain='.swiggy.com',
            path='/'
        ))

        await asyncio.sleep(0.5)
        return True
    except Exception as e:
        print(f"[Instamart] Location set error: {e}")
    return False

async def search(page, search_term):
    encoded = urllib.parse.quote(search_term)
    print(f"[Instamart] Searching for: {search_term}")

    try:
        search_url = f"https://www.swiggy.com/instamart/search?query={encoded}"
        await page.get(search_url)

        if 'blocked' in page.url or 'captcha' in page.url:
            await asyncio.sleep(3)
            await page.get(search_url)

        try:
            await wait_for_selector(page, '[data-testid="item-collection-card-full"], [data-testid="item-collection-card"]', timeout=15)
        except Exception:
            pass

        return await extract_from_html(page)
    except Exception as e:
        print(f"[Instamart] Search error: {e}")
        return []

async def extract_from_html(page):
    products = []
    try:
        cards = await page.select_all('[data-testid="item-collection-card-full"], [data-testid="item-collection-card"]')
        for idx, card in enumerate(cards):
            try:
                name_el = await card.select('._1lbNR')
                name = name_el.text if name_el and name_el.text else "Unknown"

                price_el = await card.select('._2jn41')
                price = price_el.text if price_el and price_el.text else "N/A"

                orig_el = await card.select('._3eAjW._2jn41._1VrXB')
                orig_price = orig_el.text if orig_el and orig_el.text else None

                qty_el = await card.select('._3wq_F')
                quantity = qty_el.text if qty_el and qty_el.text else ""

                img_el = await card.select('img._16I1D, img[alt]')
                image_url = img_el.attrs.get("src") if img_el and hasattr(img_el, "attrs") else ""

                discount_el = await card.select('[data-testid="offer-text"]')
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
                    "id": f"im_{idx}",
                    "name": name,
                    "price": price,
                    "originalPrice": orig_price,
                    "savings": savings,
                    "quantity": quantity,
                    "deliveryTime": "15min",
                    "discount": discount,
                    "imageUrl": image_url,
                    "available": True,
                    "source": "instamart"
                })
            except Exception:
                pass
    except Exception as e:
        print(f"[Instamart] Extraction error: {e}")

    return products
