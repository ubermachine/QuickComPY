import asyncio
import zendriver as zd
from scrapers import instamart

async def main():
    print("Starting zendriver for Instamart...")
    browser = await zd.start(config=zd.Config(sandbox=False, headless=True))
    try:
        page = await browser.get('https://www.swiggy.com/instamart', new_tab=True)
        await asyncio.sleep(10)
        await instamart.set_location(page, "bangalore")
        print("Testing search for 'milk'")
        products = await instamart.search(page, 'milk')
        for p in products:
            print(p['name'], p['price'])
        print(f"Total products found: {len(products)}")
        if not products:
            html = await page.evaluate("document.body.innerHTML")
            with open("instamart_debug.html", "w", encoding="utf-8") as f:
                f.write(html)
            print("Saved instamart_debug.html")
        await page.close()
    finally:
        await browser.stop()

if __name__ == "__main__":
    asyncio.run(main())
