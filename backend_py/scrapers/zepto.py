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
    
    try:
        # Establish domain session
        await page.get("https://www.zepto.com/")
        await asyncio.sleep(1.5)
        
        # Inject location session cookies
        await inject_location_cookies(page, pincode, lat, lon)
        
        # Navigate to search URL
        await page.get(f"https://www.zepto.com/search?query={encoded}")
        await asyncio.sleep(6)
        
        # Check serviceability on search page and fall back if not serviceable
        cookies = await page.send(zd.cdp.network.get_cookies())
        serviceable = True
        for c in cookies:
            if c.name == 'serviceability':
                val = urllib.parse.unquote(c.value).lower().replace(" ", "")
                if '"serviceable":false' in val:
                    serviceable = False
                    break
                
        if not serviceable:
            print("[Zepto] Search page is not serviceable. Re-injecting Noida fallback cookies and reloading...")
            pincode = '201301'
            lat = '28.5821195'
            lon = '77.3266991'
            await inject_location_cookies(page, pincode, lat, lon)
            await page.get(f"https://www.zepto.com/search?query={encoded}")
            await asyncio.sleep(6)
            try:
                h = await page.get_content()
                with open("zepto_fallback_search.html", "w", encoding="utf-8") as f:
                    f.write(h)
                print(f"[Zepto] Saved fallback HTML to zepto_fallback_search.html, len={len(h)}")
            except Exception as e:
                print(f"[Zepto] Error saving debug html: {e}")
            
        products = await extract_from_html(page)
        
        # Retry once if 0 products
        if not products:
            print("[Zepto] No products found, waiting 3s and retrying...")
            await asyncio.sleep(3)
            products = await extract_from_html(page)
            
        return products
    except Exception as e:
        print(f"[Zepto] Search error: {e}")
        return []

async def extract_from_html(page):
    """Extract products from Zepto search page"""
    try:
        return await page.evaluate("""(() => {
            const products = [];
            
            // Find product cards - multiple selectors for resilience
            const cards = document.querySelectorAll(
                'a[href*="/pn/"], a.B4vNQ, a[data-testid="product-card"], [class*="ProductCard"], [data-testid="product-card"]'
            );
            
            for (const card of cards) {
                try {
                    const text = card.textContent.replace(/\\s+/g, ' ').trim();
                    if (!text || text.length < 10 || !text.includes('₹')) continue;
                    
                    // Name: from data-slot-id or image alt (skip if neither)
                    let name = '';
                    const nameEl = card.querySelector('[data-slot-id="ProductName"]');
                    if (nameEl) {
                        name = nameEl.textContent.trim();
                    } else {
                        // Fallback: try image alt attribute
                        const img = card.querySelector('img');
                        name = img ? (img.alt || '').trim() : '';
                        if (!name) continue;
                    }
                    if (!name || name.length < 2) continue;
                    
                    // Quantity
                    let quantity = '1 item';
                    const packEl = card.querySelector('[data-slot-id="PackSize"]');
                    if (packEl) {
                        quantity = packEl.textContent.trim();
                    }
                    
                    // Prices: try DOM selector first, fall back to regex
                    let priceEl = card.querySelector('div[data-slot-id="EdlpPrice"] span');
                    let priceTxt = priceEl ? priceEl.textContent.trim() : '';
                    const prices = priceTxt ? [priceTxt] : (text.match(/₹[0-9,]+/g) || []);
                    let price = prices.length > 0 ? '₹' + prices[0].replace(/[^0-9.]/g, '') : 'N/A';
                    let origPrice = null;
                    if (prices.length >= 2) {
                        const second = '₹' + prices[1].replace(/[^0-9.]/g, '');
                        if (second !== price) origPrice = second;
                    }
                    
                    // Image
                    const img = card.querySelector('img');
                    const imageUrl = img ? (img.src || img.getAttribute('data-src') || '') : '';
                    
                    // Availability
                    const isOutOfStock = (card.textContent || '').toLowerCase().includes('out of stock');
                    
                    // Savings
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
                        id: 'zp_' + products.length,
                        name: name.replace(/\\s+/g, ' ').trim(),
                        price,
                        originalPrice: origPrice,
                        savings,
                        quantity,
                        deliveryTime: '10 mins',
                        discount,
                        imageUrl,
                        available: !isOutOfStock,
                        source: 'zepto'
                    });
                } catch(e) {}
            }
            
            return products.slice(0, 8);
        })()""")
    except Exception as e:
        print(f"[Zepto] HTML extraction error: {e}")
        return []