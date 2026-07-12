import asyncio
import zendriver as zd
from scrapers import jiomart

async def main():
    print("Starting zendriver for JioMart...")
    browser = await zd.start(config=zd.Config(sandbox=False, headless=True))
    try:
        page = await browser.get('https://www.jiomart.com', new_tab=True)
        await asyncio.sleep(2)
        print("Testing search for 'milk'")
        products = await jiomart.search(page, 'milk')
        for p in products:
            print(p['name'], p['price'])
        print(f"Total products found: {len(products)}")
        if not products:
            html = await page.evaluate("document.body.innerHTML")
            with open("jiomart_debug.html", "w", encoding="utf-8") as f:
                f.write(html)
            print("Saved jiomart_debug.html")
        await page.close()
    finally:
        await browser.stop()

if __name__ == "__main__":
    asyncio.run(main())
