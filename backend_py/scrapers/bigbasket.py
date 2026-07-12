import urllib.parse
import asyncio
import json
import re
import time
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

    try:
        await page.get(f"https://www.bigbasket.com/ps/?q={encoded}")
        await asyncio.sleep(5)

        products = await extract_from_html(page)

        if not products:
            print("[Bigbasket] No products found, retrying after 3s...")
            await asyncio.sleep(3)
            products = await extract_from_html(page)

        return products
    except Exception as e:
        print(f"[Bigbasket] Search error: {e}")
        return []

async def extract_from_html(page):
    """Extract products from Bigbasket rendered Next.js page"""
    try:
        return await page.evaluate("""(function() {
            var products = [];
            var allLi = document.querySelectorAll('li');
            for (var i = 0; i < allLi.length; i++) {
                var li = allLi[i];
                var text = (li.textContent || '').replace(/\\s+/g, ' ').trim();
                if (text.indexOf('\\u20B9') < 0 || text.length < 35) continue;
                if (text.indexOf('Shop by') >= 0 || text.indexOf('Category') >= 0 || text.indexOf('Filter') >= 0) continue;
                
                try {
                    var img = li.querySelector('img');
                    var imageUrl = img ? (img.src || img.getAttribute('data-src') || '') : '';
                    
                    var parts = text.split('\\u20B9');
                    if (parts.length < 2) continue;
                    
                    var beforePrice = parts[0].trim();
                    beforePrice = beforePrice.replace(/^\\d+\\s*mins?\\s*/i, '').trim();
                    beforePrice = beforePrice.replace(/\\b(?:ADD|Add|add|BUY|Buy|buy)\\s*$/i, '').trim();
                    beforePrice = beforePrice.replace(/\\d+\\.?\\d*\\s*Ratings?\\s*/ig, '').trim();
                    beforePrice = beforePrice.replace(/\\(?[\\d.]+[kK]?\\)?\\s*$/, '').trim();
                    
                    var name = beforePrice.replace(/^\\d+\\s*/, '').trim();
                    if (!name || name.length < 3) continue;
                    
                    var priceMatch = text.match(/\\u20B9\\s*[\\d,]+(?:\\.\\d{1,2})?/);
                    var price = priceMatch ? priceMatch[0].trim() : 'N/A';
                    
                    var allPrices = text.match(/\\u20B9\\s*[\\d,]+(?:\\.\\d{1,2})?/g) || [];
                    var origPrice = (allPrices.length > 1 && allPrices[1] !== price) ? allPrices[1].trim() : null;
                    
                    var quantity = '';
                    var qtyMatch = text.match(/(\\d+\\s*(?:g|kg|ml|l|L|pc|pcs|pack|piece|pouch|strip|tablet|sachet|bottle|box|can|jar|tin|tube|pair|set))\\b/i);
                    if (qtyMatch) quantity = qtyMatch[1];
                    
                    var deliveryTime = 'Standard Delivery';
                    var timeMatch = text.match(/(\\d+)\\s*mins?/i);
                    if (timeMatch) deliveryTime = timeMatch[0];
                    
                    var savings = null;
                    var discount = null;
                    if (price !== 'N/A' && origPrice) {
                        var spVal = parseFloat(price.replace(/[^0-9.]/g, ''));
                        var mrpVal = parseFloat(origPrice.replace(/[^0-9.]/g, ''));
                        if (mrpVal > spVal) {
                            savings = '\\u20B9' + (mrpVal - spVal).toFixed(2);
                            discount = Math.round(((mrpVal - spVal) / mrpVal) * 100) + '% OFF';
                        }
                    }
                    
                    products.push({
                        id: 'bb_' + products.length,
                        name: name.substring(0, 200),
                        price: price,
                        originalPrice: origPrice,
                        savings: savings,
                        quantity: quantity,
                        deliveryTime: deliveryTime,
                        discount: discount,
                        imageUrl: imageUrl,
                        available: text.toLowerCase().indexOf('out of stock') < 0,
                        source: 'bigbasket'
                    });
                } catch(e) {}
            }
            
            var seen = {};
            var unique = [];
            for (var j = 0; j < products.length && unique.length < 8; j++) {
                var key = products[j].name.substring(0, 25);
                if (!seen[key]) {
                    seen[key] = true;
                    unique.push(products[j]);
                }
            }
            return unique;
        })()""")
    except Exception as e:
        print(f"[Bigbasket] HTML extraction error: {e}")
        return []
