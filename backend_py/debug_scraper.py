import asyncio
import zendriver as zd

async def main():
    print("Starting zendriver...")
    browser = await zd.start(config=zd.Config(sandbox=False, headless=True))
    print("Browser started.")

    try:
        page = await browser.get('https://www.zepto.com/', new_tab=True)
        await asyncio.sleep(3)
        
        from backend_py.scrapers import zepto
        await zepto.set_location(page, "201306")
        
        await page.get('https://www.zepto.com/search?q=milk')
        await asyncio.sleep(5)
        
        script = """
        (() => {
            const products = [];
            const cards = document.querySelectorAll('a[data-testid="product-card"], a[href*="/pn/"]');
            cards.forEach((card, idx) => {
                try {
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

                    const priceNodes = [];
                    const walkerPrice = document.createTreeWalker(card, NodeFilter.SHOW_TEXT, null, false);
                    while (node = walkerPrice.nextNode()) {
                        const t = node.textContent.trim();
                        if (t.includes('₹') && /\\d+/.test(t)) {
                            priceNodes.push(t);
                        }
                    }
                    const price = priceNodes[0] || 'N/A';
                    const origPrice = (priceNodes[1] && priceNodes[1] !== price) ? priceNodes[1] : null;

                    products.push({ name, price, origPrice });
                } catch(e) {}
            });
            return products;
        })()
        """
        res = await page.evaluate(script)
        # Safe ASCII backslash replacement print
        safe_str = repr(res).encode('ascii', 'backslashreplace').decode('ascii')
        print("SAFE_RES:", safe_str)
        await page.close()
    except Exception as e:
        print("Error:", e)
    finally:
        await browser.stop()

if __name__ == "__main__":
    asyncio.run(main())
