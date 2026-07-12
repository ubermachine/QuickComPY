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
        script = f"""
        (() => {{
            const lat = {coords['lat']};
            const lng = {coords['lng']};
            const address = "{coords['address']}";
            const locationData = {{
                lat: lat, lng: lng, address: address,
                area: address.split(',')[0],
                city: address.split(',')[1] ? address.split(',')[1].trim() : '',
                areaId: '', latlng: `${{lat}},${{lng}}`
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
        if "swiggy.com/instamart" not in page.url:
            await page.get("https://www.swiggy.com/instamart")
            await asyncio.sleep(2)
        search_url = f"https://www.swiggy.com/instamart/search?query={encoded}"
        await page.get(search_url)
        await asyncio.sleep(5)
        
        html = await page.get_content()
        if "challenge-container" in html or "AwsWafIntegration" in html:
            print("[Instamart] WAF challenge detected, waiting for resolution...")
            await asyncio.sleep(4)
            await page.reload()
            await asyncio.sleep(4)
            
        return await extract_from_html(page)
    except Exception as e:
        print(f"[Instamart] Search error: {e}")
        return []

async def extract_from_html(page):
    """Extract products from Instamart rendered page using BeautifulSoup"""
    try:
        html = await page.get_content()
        from bs4 import BeautifulSoup
        import re
        
        soup = BeautifulSoup(html, 'html.parser')
        products = []
        
        # Look for the product card structures we identified earlier
        # Find all divs that contain an image and have some text
        item_cards = soup.select('div[data-testid="item-collection-card"]')
        
        for card in item_cards:
            try:
                root = card.parent
                if not root: continue
                
                img_el = root.find('img')
                if not img_el or not img_el.get('src'): continue
                img_url = img_el['src']
                
                # Extract all text segments that are direct text or in childless elements
                text_segments = [el.text.strip() for el in root.find_all(string=True) if el.text.strip()]
                
                name = "Unknown"
                quantity = "1 item"
                price = ""
                orig_price = ""
                discount = ""
                
                # Name is usually after MINS
                for i, t in enumerate(text_segments):
                    if "MINS" in t.upper() and i + 1 < len(text_segments):
                        name = text_segments[i+1]
                        break
                
                if name == "Unknown" and len(text_segments) > 1:
                    name = text_segments[1]
                    
                # Quantity
                for t in text_segments:
                    if re.search(r'(Pieces|Piece|g|kg|ml|L|Pack)', t, re.I) and len(t) < 25 and "MINS" not in t.upper():
                        quantity = t
                        break
                        
                # Prices (numbers only)
                nums = [t for t in text_segments if re.match(r'^\d+$', t)]
                if nums:
                    price = "₹" + nums[0]
                    orig_price = "₹" + nums[1] if len(nums) > 1 else price
                    
                # Discount
                for t in text_segments:
                    if "% OFF" in t:
                        discount = t
                        break
                        
                # Duplicate check
                if any(p['name'] == name for p in products):
                    continue
                    
                if nums:
                    products.append({
                        'id': 'im_' + str(len(products)),
                        'name': name,
                        'price': price,
                        'originalPrice': orig_price,
                        'savings': None,
                        'quantity': quantity,
                        'deliveryTime': '15 mins',
                        'discount': discount,
                        'imageUrl': img_url,
                        'available': True,
                        'source': 'instamart'
                    })
            except Exception as e:
                pass
                
        return products
    except Exception as e:
        print(f"[Instamart] HTML extraction error: {e}")
        return []