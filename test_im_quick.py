import asyncio
import json
import zendriver as zd
from backend_py.scrapers.instamart import search, set_location

async def main():
    config = zd.Config(headless=True, sandbox=False)
    browser = await zd.start(config=config)
    page = await browser.get('about:blank', new_tab=True)
    
    print("=== Testing Instamart API Interception ===\n")
    
    print("1. Setting location to 201306 (Noida)...")
    success = await set_location(page, '201306')
    print(f"   Location set: {success}\n")
    
    print("2. Searching for 'milk'...")
    results = await search(page, "milk")
    print(f"\n   Got {len(results)} products!\n")
    
    for i, r in enumerate(results):
        name = r['name'].encode('ascii', 'replace').decode()
        price = r['price'].replace('\u20b9', 'Rs.')
        orig = (r.get('originalPrice') or '').replace('\u20b9', 'Rs.')
        disc = r.get('discount', '') or ''
        qty = r.get('quantity', '')
        img = 'YES' if r.get('imageUrl') else 'NO'
        print(f"   [{i+1}] {name} | {qty} | {price} (was {orig}) {disc} | img={img}")
    
    await browser.stop()

if __name__ == "__main__":
    asyncio.run(main())
