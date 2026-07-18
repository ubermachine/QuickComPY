"""Verify Bigbasket and Zepto fixes"""
import sys, asyncio, zendriver as zd
sys.stdout.reconfigure(encoding='utf-8')

_STEALTH = """Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
Object.defineProperty(navigator, 'plugins', { get: () => [1,2,3,4,5] });
Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
window.chrome = { runtime: {} };"""

async def test_one(browser, name, module, search_term, needs_loc=True):
    page = await browser.get("about:blank", new_tab=True)
    await page.send(zd.cdp.page.add_script_to_evaluate_on_new_document(source=_STEALTH))
    try:
        if needs_loc:
            await module.set_location(page, "110001")
        products = await module.search(page, search_term)
        if products:
            print(f"[OK] {name}: {len(products)} products")
            print(f"     [{products[0]['source']}] {products[0]['name'][:60]} - {products[0]['price']} {products[0].get('quantity','')}")
            if len(products) > 1:
                print(f"     [{products[1]['source']}] {products[1]['name'][:60]} - {products[1]['price']} {products[1].get('quantity','')}")
        else:
            print(f"[FAIL] {name}: 0 products")
            try:
                t = await page.evaluate("document.title")
                print(f"       Title: '{t}'")
            except: pass
    except Exception as e:
        print(f"[ERR] {name}: {e}")
    finally:
        await page.close()

async def main():
    config = zd.Config(sandbox=False, headless=True)
    browser = await zd.start(config=config)
    
    from backend_py.scrapers import bigbasket, zepto
    
    print("Testing Bigbasket (content-based extraction)...")
    await test_one(browser, "Bigbasket", bigbasket, "milk")
    
    print("\nTesting Zepto (CDP cookie, no domain nav)...")
    await test_one(browser, "Zepto", zepto, "milk")
    
    await browser.stop()
    print("\nDone!")

asyncio.run(main())
