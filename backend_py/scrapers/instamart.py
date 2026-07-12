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
        if "swiggy.com/instamart" not in page.url:
            await page.get("https://www.swiggy.com/instamart")
            await asyncio.sleep(2)

        search_url = f"https://www.swiggy.com/instamart/search?query={encoded}"
        await page.get(search_url)
        
        html = await page.get_content()
        if "challenge-container" in html or "AwsWafIntegration" in html or "Something went wrong" in html or "Try Again" in html:
            print("[Instamart] WAF challenge detected, waiting for resolution...")
            await page.evaluate("""
                const btn = Array.from(document.querySelectorAll('button')).find(b => b.innerText && b.innerText.includes('Try Again'));
                if (btn) btn.click();
            """)
            await asyncio.sleep(4)
            await page.reload()
            await asyncio.sleep(4)
            
        return await extract_from_html(page)
    except Exception as e:
        print(f"[Instamart] Search error: {e}")
        return []

async def extract_from_html(page):
    try:
        return await page.evaluate(r"""
        (() => {
            const products = [];
            const titles = document.querySelectorAll('._1lbNR, [class*="productTitle"], h3');
            titles.forEach((titleEl, idx) => {
                try {
                    let card = titleEl.parentElement;
                    while(card && card !== document.body && !card.querySelector('img')) {
                        card = card.parentElement;
                    }
                    if (!card) card = titleEl.closest('div');
                    
                    const name = titleEl.textContent.trim();
                    if (!name || name === 'Unknown') return;
                    
                    // Use textContent or innerText to extract price and qty
                    const textLines = (card.innerText || '').split('\\n').map(l => l.trim()).filter(l => l);
                    
                    let price = 'N/A';
                    let origPrice = null;
                    let quantity = '1 item';
                    let discount = null;
                    
                    // Look for price line containing ₹
                    for (let i = 0; i < textLines.length; i++) {
                        const line = textLines[i];
                        if (line.includes('₹')) {
                            // Extract numbers
                            const parts = line.split('₹');
                            if (parts.length > 1) {
                                // Sometimes orig price and current price are on the same line, or separate lines.
                                const valStr = parts[1].replace(/[^0-9.]/g, '');
                                if (valStr) price = '₹' + valStr;
                            }
                            if (parts.length > 2) {
                                const valStr2 = parts[2].replace(/[^0-9.]/g, '');
                                if (valStr2) {
                                    origPrice = price; // The first was MRP
                                    price = '₹' + valStr2; // The second is selling price
                                }
                            }
                            break;
                        }
                    }
                    
                    // Quantity often ends with g, kg, ml, L, pcs
                    for (let i = 0; i < textLines.length; i++) {
                        const line = textLines[i].toLowerCase();
                        if (line.match(/^[0-9.]+\s*(g|kg|ml|l|pc|pcs|pack)$/) || line.match(/^[0-9]+\s*x\s*[0-9]+.*$/)) {
                            quantity = textLines[i];
                            break;
                        }
                    }
                    
                    // Attempt fallback if price still N/A
                    if (price === 'N/A') {
                        const priceEl = card.querySelector('[class*="price"], ._2jn41');
                        if (priceEl && priceEl.textContent.includes('₹')) {
                            price = '₹' + priceEl.textContent.replace(/[^0-9.]/g, '').trim();
                        }
                    }
                    
                    const imgEl = card.querySelector('img._16I1D, img[alt], img');
                    const imageUrl = imgEl ? imgEl.src : '';
                    
                    let savings = null;
                    if (price !== 'N/A' && origPrice) {
                        const spVal = parseFloat(price.replace(/[^0-9.]/g, ''));
                        const mrpVal = parseFloat(origPrice.replace(/[^0-9.]/g, ''));
                        if (mrpVal > spVal) {
                            savings = '₹' + (mrpVal - spVal).toFixed(2);
                        }
                    }
                    
                    products.push({
                        id: 'im_' + idx,
                        name,
                        price,
                        originalPrice: origPrice,
                        savings,
                        quantity,
                        deliveryTime: "15 mins",
                        discount,
                        imageUrl,
                        available: true,
                        source: 'instamart'
                    });
                } catch(e) {}
            });
            return products;
        })()
        """)
    except Exception as e:
        print(f"[Instamart] HTML extraction error: {e}")
        return []
