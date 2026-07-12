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
        await asyncio.sleep(4)

        # Extract products from the rendered DOM
        return await extract_from_html(page)
    except Exception as e:
        print(f"[Bigbasket] Search error: {e}")
        return []

async def extract_from_html(page):
    """Extract products from Bigbasket rendered Next.js page using DOM analysis"""
    try:
        return await page.evaluate("""() => {
            const products = [];
            
            // Find product cards by looking for images near prices
            const candidates = new Set();
            const images = document.querySelectorAll('img[src*="bbassets"], img[src*="bigbasket"], img[src*="bb"]');
            
            if (images.length === 0) {
                // Fallback: find any img near ₹ text
                const allImgs = document.querySelectorAll('img');
                for (const img of allImgs) {
                    let card = img.parentElement;
                    for (let i = 0; i < 8 && card; i++) {
                        const ct = (card.textContent || '');
                        if (ct.includes('₹') && ct.length > 50 && ct.length < 3000) {
                            candidates.add(card);
                            break;
                        }
                        card = card.parentElement;
                    }
                }
            } else {
                images.forEach(img => {
                    let card = img.parentElement;
                    for (let i = 0; i < 8 && card; i++) {
                        const ct = (card.textContent || '');
                        if (ct.includes('₹') && ct.length > 50 && ct.length < 3000) {
                            candidates.add(card);
                            break;
                        }
                        card = card.parentElement;
                    }
                });
            }
            
            // Method 2: Also look at list items in grids
            document.querySelectorAll('li, [class*="product"], [class*="sku"], [class*="card"]').forEach(el => {
                const t = el.textContent || '';
                if (t.includes('₹') && t.length > 50 && t.length < 3000) {
                    candidates.add(el);
                }
            });
            
            for (const card of candidates) {
                try {
                    const text = card.textContent.replace(/\\s+/g, ' ').trim();
                    
                    // Extract image
                    const img = card.querySelector('img');
                    const imageUrl = img ? (img.src || img.getAttribute('data-src') || '') : '';
                    if (!imageUrl && !text.includes('₹')) continue;
                    
                    // Extract name - usually the longest text before ₹
                    const parts = text.split('₹');
                    let name = parts[0].trim();
                    // Clean up name
                    name = name.replace(/^\\d+\\s*/, '').replace(/\\s+/g, ' ').trim();
                    if (!name || name.length < 3) continue;
                    
                    // Extract prices
                    const prices = text.match(/₹[0-9,.]+/g) || [];
                    const price = prices.length > 0 ? prices[0].trim() : 'N/A';
                    const origPrice = (prices.length > 1 && prices[1] !== price) ? prices[1].trim() : null;
                    
                    // Extract quantity/weight
                    let quantity = '';
                    const qtyMatch = text.match(/(\\d+\\s*(g|kg|ml|l|pc|pcs|pack|piece|pouch))/i);
                    if (qtyMatch) quantity = qtyMatch[1];
                    
                    let savings = null;
                    let discount = null;
                    if (price && price !== 'N/A' && origPrice) {
                        const spVal = parseFloat(price.replace(/[^0-9.]/g, ''));
                        const mrpVal = parseFloat(origPrice.replace(/[^0-9.]/g, ''));
                        if (mrpVal > spVal) {
                            savings = '₹' + (mrpVal - spVal).toFixed(2);
                            discount = Math.round(((mrpVal - spVal) / mrpVal) * 100) + '% OFF';
                        }
                    }
                    
                    products.push({
                        id: 'bb_' + products.length,
                        name: name.substring(0, 200),
                        price,
                        originalPrice: origPrice,
                        savings,
                        quantity,
                        deliveryTime: 'Standard Delivery',
                        discount,
                        imageUrl,
                        available: !text.toLowerCase().includes('out of stock'),
                        source: 'bigbasket'
                    });
                } catch(e) {}
            }
            
            // Deduplicate by name
            const seen = new Set();
            return products.filter(p => {
                const key = p.name.substring(0, 25);
                if (seen.has(key)) return false;
                seen.add(key);
                return true;
            }).slice(0, 50);
        }""")
    except Exception as e:
        print(f"[Bigbasket] HTML extraction error: {e}")
        return []