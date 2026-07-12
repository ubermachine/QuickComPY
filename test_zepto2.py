import asyncio
import zendriver as zd
from backend_py.scrapers.zepto import set_location, search

async def main():
    browser = await zd.start(config=zd.Config(sandbox=False, headless=True))
    try:
        print("Tab 1: Setting location...")
        tab1 = await browser.get('about:blank', new_tab=True)
        success = await set_location(tab1, "110001")
        print("Location set success:", success)
        await tab1.close()
        
        print("Tab 2: Searching...")
        tab2 = await browser.get('about:blank', new_tab=True)
        res = await search(tab2, "eggs")
        print("Found products:", len(res))
        await tab2.close()
    finally:
        await browser.stop()

if __name__ == "__main__":
    asyncio.run(main())
