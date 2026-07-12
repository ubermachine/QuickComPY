import sys
if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

import asyncio
import zendriver as zd
from backend_py.scrapers.jiomart import set_location, search

async def test_vendor(browser, service_name, module):
    print(f"[{service_name}] Setting location...")
    page1 = await browser.get("about:blank")
    try:
        await module.set_location(page1, "110001")
        await page1.save_screenshot("jm_debug_pin.png")
        html = await page1.get_content()
        with open("jm_debug_pin.html", "w", encoding="utf-8") as f:
            f.write(html)
    finally:
        await page1.close()

async def main():
    browser = await zd.start(config=zd.Config(sandbox=False, headless=True))
    try:
        await test_vendor(browser, "JioMart", __import__('backend_py.scrapers.jiomart', fromlist=['set_location']))
        
        page2 = await browser.get('about:blank', new_tab=True)
        products = await search(page2, "eggs")
        print(f"Found {len(products)} products on JioMart")
        if products:
            print(products[0])
        else:
            # Let's see the DOM
            html = await page2.get_content()
            with open("jm_debug.html", "w", encoding="utf-8") as f:
                f.write(html)
            await page2.save_screenshot("jm_debug.png")
            print("Saved debug screenshot and HTML")
    finally:
        await browser.stop()

if __name__ == "__main__":
    asyncio.run(main())
