import urllib.parse
import asyncio
import json

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

async def set_location(page, location):
    print(f"[Instamart] Attempting to set location to {location}")

    city_key = location.lower().strip()
    coords = CITY_COORDINATES.get(city_key, CITY_COORDINATES['bangalore'])

    try:
        if "swiggy.com/instamart" not in page.url:
            await page.goto("https://www.swiggy.com/instamart", wait_until="domcontentloaded", timeout=60000)

        # Inject location via JS
        script = """
        (lat, lng, address) => {
            const locationData = {
                lat: lat,
                lng: lng,
                address: address,
                area: address.split(',')[0],
                city: address.split(',')[1] ? address.split(',')[1].trim() : '',
                areaId: '',
                latlng: `${lat},${lng}`
            };
            try { localStorage.setItem('userLocation', JSON.stringify(locationData)); } catch(e) {}
            try { localStorage.setItem('swiggy_location', JSON.stringify(locationData)); } catch(e) {}
            try { localStorage.setItem('IM_location', JSON.stringify(locationData)); } catch(e) {}
            try { sessionStorage.setItem('userLocation', JSON.stringify(locationData)); } catch(e) {}
        }
        """
        await page.evaluate(script, [coords['lat'], coords['lng'], coords['address']])

        await page.context.add_cookies([{
            'name': 'userLocation',
            'value': json.dumps({'lat': coords['lat'], 'lng': coords['lng']}),
            'domain': '.swiggy.com',
            'path': '/'
        }])

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
        await page.goto(search_url, wait_until="domcontentloaded", timeout=60000)

        if 'blocked' in page.url or 'captcha' in page.url:
            await asyncio.sleep(3)
            await page.goto(search_url, wait_until="domcontentloaded", timeout=60000)

        try:
            await page.wait_for_selector('[data-testid="item-collection-card-full"], [data-testid="item-collection-card"]', timeout=15000)
        except Exception:
            pass

        return await extract_from_html(page)
    except Exception as e:
        print(f"[Instamart] Search error: {e}")
        return []

async def extract_from_html(page):
    products = []
    try:
        cards = await page.query_selector_all('[data-testid="item-collection-card-full"], [data-testid="item-collection-card"]')
        for idx, card in enumerate(cards):
            try:
                name_el = await card.query_selector('._1lbNR')
                name = await name_el.inner_text() if name_el else "Unknown"

                price_el = await card.query_selector('._2jn41')
                price = await price_el.inner_text() if price_el else "N/A"

                orig_el = await card.query_selector('._3eAjW._2jn41._1VrXB')
                orig_price = await orig_el.inner_text() if orig_el else None

                qty_el = await card.query_selector('._3wq_F')
                quantity = await qty_el.inner_text() if qty_el else ""

                img_el = await card.query_selector('img._16I1D, img[alt]')
                image_url = await img_el.get_attribute("src") if img_el else ""

                discount_el = await card.query_selector('[data-testid="offer-text"]')
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
