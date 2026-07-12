import asyncio
import zendriver as zd
from backend_py.scrapers import blinkit, bigbasket, jiomart, zepto, instamart

SERVICES = ["blinkit", "bigbasket", "jiomart", "zepto", "instamart"]
SCRAPERS = {
    "blinkit": blinkit,
    "bigbasket": bigbasket,
    "jiomart": jiomart,
    "zepto": zepto,
    "instamart": instamart
}

async def set_loc(browser, svc):
    print(f"Setting location {svc}...")
    page = await browser.get('about:blank', new_tab=True)
    try:
        await SCRAPERS[svc].set_location(page, "110001")
    finally:
        await page.close()

async def search_svc(browser, svc, search_term):
    print(f"Searching {svc}...")
    page = await browser.get('about:blank', new_tab=True)
    try:
        products = await asyncio.wait_for(SCRAPERS[svc].search(page, search_term), timeout=30.0)
        return svc, len(products)
    except Exception as e:
        print(f"Error {svc}: {e}")
        return svc, 0
    finally:
        await page.close()

async def main():
    browser = await zd.start(config=zd.Config(sandbox=False, headless=True))
    try:
        # Sequential location set
        for s in SERVICES:
            await set_loc(browser, s)
            
        print("\n--- Starting concurrent search ---")
        results = await asyncio.gather(*[search_svc(browser, s, "eggs") for s in SERVICES])
        print("Results:", results)
    finally:
        await browser.stop()

if __name__ == "__main__":
    asyncio.run(main())
