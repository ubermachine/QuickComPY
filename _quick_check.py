"""Quick check: test all 4 scrapers live"""
import sys, asyncio, zendriver as zd
sys.stdout.reconfigure(encoding='utf-8')

_STEALTH = """Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
Object.defineProperty(navigator, 'plugins', { get: () => [1,2,3,4,5] });
Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
window.chrome = { runtime: {} };"""

async def test_scraper(browser, name, module, search_term, needs_location=True):
    page = await browser.get("about:blank", new_tab=True)
    await page.send(zd.cdp.page.add_script_to_evaluate_on_new_document(source=_STEALTH))
    try:
        if needs_location:
            await module.set_location(page, "110001")
        products = await module.search(page, search_term)
        if products:
            print(f"[OK] {name}: {len(products)} products")
            print(f"     First: {products[0]['name']} - {products[0]['price']}")
        else:
            print(f"[FAIL] {name}: 0 products returned")
            # Check page state
            try:
                title = await page.evaluate("document.title")
                print(f"       Title: {title}")
            except:
                pass
    except Exception as e:
        print(f"[ERR] {name}: {type(e).__name__} - {str(e)[:80]}")
    finally:
        await page.close()

async def main():
    config = zd.Config(
        sandbox=False,
        headless=True,
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36',
        disable_webrtc=True,
    )
    browser = await zd.start(config=config)
    
    from backend_py.scrapers import blinkit, bigbasket, jiomart, zepto
    
    print("Testing all scrapers...\n")
    await test_scraper(browser, "Blinkit", blinkit, "milk")
    await test_scraper(browser, "Bigbasket", bigbasket, "milk")
    await test_scraper(browser, "JioMart", jiomart, "milk")
    await test_scraper(browser, "Zepto", zepto, "milk")
    
    await browser.stop()
    print("\nDone!")

asyncio.run(main())
