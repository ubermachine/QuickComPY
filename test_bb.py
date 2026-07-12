import sys
if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

import asyncio
import zendriver as zd
from backend_py.scrapers.bigbasket import set_location, search

async def main():
    print("Starting browser...")
    browser = await zd.start(config=zd.Config(sandbox=False, headless=True))
    try:
        # First tab for setting location
        tab1 = await browser.get('about:blank', new_tab=True)
        print("Setting location...")
        success = await set_location(tab1, "110001")
        print("Location set success:", success)
        
        # Second tab for searching (simulating what app.py does)
        tab2 = await browser.get('about:blank', new_tab=True)
        print("Searching...")
        res = await search(tab2, "eggs")
        print("Found products:", len(res))
    finally:
        await browser.stop()

if __name__ == "__main__":
    asyncio.run(main())
