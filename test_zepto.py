import sys
if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

import asyncio
import zendriver as zd
from backend_py.scrapers.zepto import set_location, search

async def main():
    print("Starting browser...")
    browser = await zd.start(config=zd.Config(sandbox=False, headless=True))
    try:
        tab = await browser.get('about:blank', new_tab=True)
        print("Setting location...")
        success = await set_location(tab, "110001")
        print("Location set success:", success)
        
        print("Searching...")
        res = await search(tab, "eggs")
        print("Found products:", len(res))
        for p in res:
            print(p)
    finally:
        await browser.stop()

if __name__ == "__main__":
    asyncio.run(main())
