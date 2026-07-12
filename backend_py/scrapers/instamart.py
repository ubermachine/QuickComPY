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
    """Extract products from Instamart rendered page"""
    try:
        return await page.evaluate("""() => {
            const products = [];
            const candidates = new Set();
            
            // Find product-like elements containing prices
            const allEls = document.querySelectorAll('a, div, section');
            for (const el of allEls) {
                const t = (el.textContent || '').trim();
                if (t.includes('₹') && t.length > 30 && t.length < 2000) {
                    // Walk up to find the card boundary
                    let card = el;
                    for (let i = 0; i < 5; i++) {
                        if (!card || card === document.body) break;
                        const ct = (card.textContent || '').trim();
                        if (card.querySelector('img') && 
                            ct.includes('₹') && 
                            ct.length > 50 && ct.length < 3000 &&
                            (ct.includes('min') || ct.includes('mins') || ct.length > 80)) {
                            candidates.add(card);
                            break;
                        }
                        card = card.parentElement;
                    }
                }
            }
            
            for (const card of candidates) {
                try {
                    const text = card.textContent.replace(/\\s+/g, ' ').trim();
                    if (!text || text.length < 20) continue;
                    
                    // Extract name - text before first ₹
                    const parts = text.split('₹');
                    let name = parts[0].trim();
                    if (!name || name.length < 2) continue;
                    name = name.replace(/^\\s*(ADD|\\+|\\d+)\\s*/i, '').trim();
                    
                    // Extract prices
                    const priceMatches = text.match(/₹[0-9,.]+/g) || [];
                    let price = 'N/A';
                    let origPrice = null;
                    if (priceMatches.length >= 1) price = priceMatches[0].trim();
                    if (priceMatches.length >= 2) {
                        const second = priceMatches[1].trim();
                        if (second !== price) origPrice = second;
                    }
                    
                    // Quantity
                    let quantity = '1 item';
                    const qtyMatch = text.match(/(\\d+\\s*(g|kg|ml|l|pc|pcs|pack|piece|count))/i);
                    if (qtyMatch) quantity = qtyMatch[1];
                    
                    // Image
                    const img = card.querySelector('img');
                    const imageUrl = img ? (img.src || img.getAttribute('data-src') || '') : '';
                    
                    let savings = null;
                    let discount = null;
                    if (price !== 'N/A' && origPrice) {
                        const spVal = parseFloat(price.replace(/[^0-9.]/g, ''));
                        const mrpVal = parseFloat(origPrice.replace(/[^0-9.]/g, ''));
                        if (mrpVal > spVal) {
                            savings = '₹' + (mrpVal - spVal).toFixed(2);
                            discount = Math.round(((mrpVal - spVal) / mrpVal) * 100) + '% OFF';
                        }
                    }
                    
                    products.push({
                        id: 'im_' + products.length,
                        name: name.substring(0, 200),
                        price,
                        originalPrice: origPrice,
                        savings,
                        quantity,
                        deliveryTime: '15 mins',
                        discount,
                        imageUrl,
                        available: true,
                        source: 'instamart'
                    });
                } catch(e) {}
            }
            
            const seen = new Set();
            return products.filter(p => {
                const key = p.name.substring(0, 20);
                if (seen.has(key)) return false;
                seen.add(key);
                return true;
            }).slice(0, 50);
        }""")
    except Exception as e:
        print(f"[Instamart] HTML extraction error: {e}")
        return []