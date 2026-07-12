import urllib.parse
import asyncio
import time
import zendriver as zd

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
    """Set location via page navigation and selection"""
    print(f"[Zepto] Attempting to set location to {location}")
    pincode = str(location).strip()[:6] if location else '110001'
    
    try:
        await page.get("https://www.zepto.com/")
        await asyncio.sleep(2)
    except Exception as e:
        print(f"[Zepto] Error navigating: {e}")
        try:
            await page.send(zd.cdp.network.set_cookie(name='location', value=pincode, domain='.zepto.com', path='/'))
        except Exception:
            pass

    try:
        location_btn = await page.select('[data-testid="user-address"]')
        if not location_btn:
            location_btn = await page.select('button[class*="location"], header button')
            
        if location_btn:
            await location_btn.click()
            await asyncio.sleep(1.5)
            input_box = await page.select('input[placeholder*="Search"], input[data-testid="location-search-input"]')
            if input_box:
                await input_box.send_keys(pincode)
                await asyncio.sleep(2.5)
                suggestions = await page.select_all('ul li, li, [class*="suggestion"], [class*="Suggestion"]')
                if suggestions:
                    await suggestions[0].click()
                    await asyncio.sleep(2)
                    buttons = await page.select_all("button")
                    for btn in buttons:
                        try:
                            btn_txt = btn.text
                            if btn_txt and any(x in btn_txt.lower() for x in ["confirm", "continue", "set"]):
                                await btn.click()
                                await asyncio.sleep(3)
                                break
                        except Exception:
                            pass
                    return True
        return False
    except Exception as e:
        print(f"[Zepto] Location set error: {e}")
    return False

async def search(page, search_term):
    encoded = urllib.parse.quote(search_term)
    print(f"[Zepto] Searching for: {search_term}")
    try:
        await page.get(f"https://www.zepto.com/search?q={encoded}")
        await asyncio.sleep(3)
        return await extract_from_html(page)
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
                'a[href*="/pn/"], a[data-testid="product-card"], [class*="ProductCard"], [data-testid="product-card"]'
            );
            
            for (const card of cards) {
                try {
                    const text = card.textContent.replace(/\\s+/g, ' ').trim();
                    if (!text || text.length < 10 || !text.includes('₹')) continue;
                    
                    // Name: from data-slot-id or first meaningful text
                    let name = '';
                    const nameEl = card.querySelector('[data-slot-id="ProductName"]');
                    if (nameEl) {
                        name = nameEl.textContent.trim();
                    } else {
                        // Fallback: find text before ₹
                        const parts = text.split('₹');
                        name = parts[0].trim();
                    }
                    if (!name || name.length < 2) continue;
                    
                    // Quantity
                    let quantity = '1 item';
                    const packEl = card.querySelector('[data-slot-id="PackSize"]');
                    if (packEl) {
                        quantity = packEl.textContent.trim();
                    }
                    
                    // Prices using regex
                    const prices = text.match(/₹[0-9,]+/g) || [];
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
            });
            
            return products;
        })()""")
    except Exception as e:
        print(f"[Zepto] HTML extraction error: {e}")
        return []