import urllib.parse
import asyncio
import time

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
    print(f"[JioMart] Attempting to set location to {location}")
    try:
        await page.get("https://www.jiomart.com/")
        await asyncio.sleep(3)
        
        # Click "Select Location Manually" if the modal appears
        await page.evaluate("""
            const btns = Array.from(document.querySelectorAll('button'));
            const manualBtn = btns.find(b => b.textContent && b.textContent.includes('Select Location Manually'));
            if (manualBtn) { manualBtn.click(); }
        """)
        await asyncio.sleep(1)
        
        # Type pin code
        await page.evaluate(f"""
            const inputs = Array.from(document.querySelectorAll('input'));
            const pinInput = inputs.find(i => i.placeholder && i.placeholder.toLowerCase().includes('pin'));
            if (pinInput) {{
                pinInput.value = '{location}';
                pinInput.dispatchEvent(new Event('input', {{ bubbles: true }}));
                pinInput.dispatchEvent(new Event('change', {{ bubbles: true }}));
            }}
        """)
        await asyncio.sleep(1)
            
        # Click apply/submit
        await page.evaluate("""
            const btns2 = Array.from(document.querySelectorAll('button'));
            const applyBtn = btns2.find(b => b.textContent && b.textContent.includes('Apply'));
            if (applyBtn) { applyBtn.click(); }
        """)
        await asyncio.sleep(2)
        return True
    except Exception as e:
        print(f"[JioMart] Location set error: {e}")
        return False

async def search(page, search_term):
    encoded = urllib.parse.quote(search_term)
    print(f"[JioMart] Searching for: {search_term}")

    try:
        # Establish session first if needed
        if "jiomart.com" not in page.url:
            await page.get("https://www.jiomart.com/")
            await asyncio.sleep(1.5)
        await page.get(f"https://www.jiomart.com/products?q={encoded}")
        await asyncio.sleep(6)

        # Wait for product cards to appear (poll up to 15s)
        await wait_for_selector(page, ".productCard__productTitle", timeout=15)

        products = await extract_from_html(page)

        # Retry once if extraction returned 0 products
        if not products:
            print("[JioMart] No products found on first attempt, retrying after 3s...")
            await asyncio.sleep(3)
            products = await extract_from_html(page)

        return products
    except Exception as e:
        print(f"[JioMart] Search error: {e}")
        return []

async def extract_from_html(page):
    try:
        return await page.evaluate("""
        (() => {
            const products = [];
            const cards = document.querySelectorAll('.productCard__cardWrapper, .plp-card');
            cards.forEach((card, idx) => {
                try {
                    if (card.className && card.className.includes('Skeleton')) return;
                    
                    const nameEl = card.querySelector('.productCard__productTitle, .plp-card-title, h3');
                    const name = nameEl ? nameEl.textContent.trim() : 'Unknown';
                    if (!name || name === 'Unknown') return;
                    
                    const priceEl = card.querySelector('.PriceContainer__currentPrice, .plp-card-price, .jm-price');
                    const price = priceEl ? priceEl.textContent.trim() : 'N/A';
                    
                    const origEl = card.querySelector('.PriceContainer__originalPrice, .plp-card-mrp, .jm-mrp');
                    const origPrice = origEl ? origEl.textContent.trim() : null;
                    
                    const qtyEl = card.querySelector('.productCard__sizeSpan, .productCard__quantitySelector, .plp-card-qty');
                    const quantity = qtyEl ? qtyEl.textContent.trim() : '';
                    
                    const imgEl = card.querySelector('.productCard__productImage, img');
                    const imageUrl = imgEl ? (imgEl.src || imgEl.getAttribute('data-src') || '') : '';
                    
                    let savings = null;
                    let discount = null;
                    if (price && origPrice) {
                        const spVal = parseFloat(price.replace(/[^0-9.]/g, ''));
                        const mrpVal = parseFloat(origPrice.replace(/[^0-9.]/g, ''));
                        if (mrpVal > spVal) {
                            savings = '₹' + (mrpVal - spVal).toFixed(2);
                            discount = Math.round(((mrpVal - spVal) / mrpVal) * 100) + '% OFF';
                        }
                    }
                    
                    products.push({
                        id: 'jm_' + idx,
                        name,
                        price,
                        originalPrice: origPrice,
                        savings,
                        quantity,
                        deliveryTime: "Standard Delivery",
                        discount,
                        imageUrl,
                        available: true,
                        source: 'jiomart'
                    });
                } catch(e) {}
            });
            return products.slice(0, 8);
        })()
        """)
    except Exception as e:
        print(f"[JioMart] HTML extraction error: {e}")
        return []
