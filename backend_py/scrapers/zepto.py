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
    print(f"[Zepto] Attempting to set location to {location}")
    try:
        await page.get("https://www.zepto.com/")
        await asyncio.sleep(2)
    except Exception as e:
        print(f"[Zepto] Error navigating: {e}")

    try:
        # Check if already set
        addr_el = await page.select('[data-testid="user-address"]')
        if addr_el:
            txt = addr_el.text
            if txt and "select" not in txt.lower() and "enter" not in txt.lower():
                print(f"[Zepto] Location already set: {txt}")
                return True

        # Click the location button
        location_btn = await page.select('[data-testid="user-address"]')
        if not location_btn:
            location_btn = await page.select('header button')
        if not location_btn:
            location_btn = await page.select('button[aria-label="Select Location"], div[class*="location-select"]')
            
        if location_btn:
            await location_btn.click()
            await asyncio.sleep(1.5)

            # Wait for search box
            input_box = await page.select('input[placeholder*="Search a new address"], input[data-testid="location-search-input"]')
            if input_box:
                await input_box.send_keys(location)
                await asyncio.sleep(2.5)

                # Find suggestions
                suggestions = await page.select_all('ul li, li, [class*="suggestion"], [class*="Suggestion"]')
                if suggestions:
                    await suggestions[0].click()
                    await asyncio.sleep(2)

                    # Confirm location if dialog/confirm button appears
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
    try:
        return await page.evaluate("""
        (() => {
            const products = [];
            const cards = document.querySelectorAll('a[data-testid="product-card"], a[href*="/pn/"], [class*="ProductCard"], [data-testid="product-card"]');
            cards.forEach((card, idx) => {
                try {
                    // Extract name (first text node length > 2 and not starting with a digit/rupee or contains key actions)
                    const textNodes = [];
                    const walker = document.createTreeWalker(card, NodeFilter.SHOW_TEXT, null, false);
                    let node;
                    while (node = walker.nextNode()) {
                        const t = node.textContent.trim();
                        if (t.length > 2 && !/^[₹\d]/.test(t) && !t.includes('ADD') && !t.includes('Qty') && !t.includes('mins') && !t.includes('OFF')) {
                            textNodes.push(t);
                        }
                    }
                    const name = textNodes[0] || 'Unknown Product';

                    // Extract price nodes
                    const priceNodes = [];
                    const walkerPrice = document.createTreeWalker(card, NodeFilter.SHOW_TEXT, null, false);
                    while (node = walkerPrice.nextNode()) {
                        const t = node.textContent.trim();
                        if (t.startsWith('₹') && /₹\\s*\\d+/.test(t)) {
                            priceNodes.push(t);
                        }
                    }
                    const price = priceNodes[0] || 'N/A';
                    const origPrice = (priceNodes[1] && priceNodes[1] !== price) ? priceNodes[1] : null;

                    // Quantity
                    const qtyEl = card.querySelector('[class*="packsize"], [class*="Packsize"], [class*="weight"], [class*="Weight"]');
                    const quantity = qtyEl ? qtyEl.textContent.trim() : '1 item';

                    // Image
                    const imgEl = card.querySelector('img');
                    const imageUrl = imgEl ? imgEl.src : '';

                    // Available
                    const cardText = card.textContent || '';
                    const available = !cardText.toLowerCase().includes('out of stock') && !cardText.toLowerCase().includes('notify');

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
                        id: 'zp_' + idx,
                        name,
                        price,
                        originalPrice: origPrice,
                        savings,
                        quantity,
                        deliveryTime: "10 mins",
                        discount,
                        imageUrl,
                        available,
                        source: 'zepto'
                    });
                } catch(e) {}
            });
            return products;
        })()
        """)
    except Exception as e:
        print(f"[Zepto] HTML extraction error: {e}")
        return []
