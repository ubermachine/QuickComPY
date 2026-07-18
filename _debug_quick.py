"""Quick debug - check if cookie took effect"""
import sys, asyncio, zendriver as zd
sys.stdout.reconfigure(encoding='utf-8')
_STEALTH = """Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
Object.defineProperty(navigator, 'plugins', { get: () => [1,2,3,4,5] });
Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
window.chrome = { runtime: {} };"""

async def main():
    config = zd.Config(sandbox=False, headless=True)
    browser = await zd.start(config=config)
    
    from backend_py.scrapers import bigbasket, zepto
    
    # Test Zepto with original flow (set location first, then search)
    print("=== Zepto with set_location first ===")
    page = await browser.get("about:blank", new_tab=True)
    await page.send(zd.cdp.page.add_script_to_evaluate_on_new_document(source=_STEALTH))
    await zepto.set_location(page, "110001")
    await page.close()
    
    page2 = await browser.get("about:blank", new_tab=True)
    await page2.send(zd.cdp.page.add_script_to_evaluate_on_new_document(source=_STEALTH))
    products = await zepto.search(page2, "milk")
    print(f"Products: {len(products)}")
    if not products:
        # Check cookie and page state
        cookies = await page2.send(zd.cdp.network.get_cookies())
        print(f"Cookies: {[(c['name'], c['value']) for c in cookies if c.get('domain','').includes('zepto')]}")
        title = await page2.evaluate("document.title")
        print(f"Title: '{title}'")
        url = await page2.evaluate("window.location.href")
        print(f"URL: {url}")
    await page2.close()
    
    # Test Bigbasket: check if the page loads
    print("\n=== Bigbasket direct check ===")
    page3 = await browser.get("about:blank", new_tab=True)
    await page3.send(zd.cdp.page.add_script_to_evaluate_on_new_document(source=_STEALTH))
    await bigbasket.set_location(page3, "110001")
    await page3.get("https://www.bigbasket.com/ps/?q=milk")
    await asyncio.sleep(6)
    
    title = await page3.evaluate("document.title")
    li_count = await page3.evaluate("document.querySelectorAll('li').length")
    has_price = await page3.evaluate("""(function() {
        var items = document.querySelectorAll('li');
        var count = 0;
        for (var i = 0; i < items.length; i++) {
            if (items[i].textContent.indexOf('\\u20B9') >= 0) count++;
        }
        return count;
    })()""")
    print(f"Title: '{title}'")
    print(f"Total li: {li_count}")
    print(f"Li with price: {has_price}")
    
    # Try the actual scrape
    products2 = await bigbasket.extract_from_html(page3)
    print(f"Extracted products: {len(products2)}")
    if products2:
        for p in products2[:3]:
            print(f"  {p['name']} - {p['price']}")
    await page3.close()
    
    await browser.stop()

asyncio.run(main())
