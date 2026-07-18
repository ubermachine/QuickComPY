import asyncio
import json
import zendriver as zd
from backend_py.scrapers.jiomart import search

async def main():
    config = zd.Config(headless=True, sandbox=False)
    browser = await zd.start(config=config)
    page = await browser.get('about:blank', new_tab=True)
    
    # We will log URLs directly here to see what API it uses
    async def log_response(event):
        if event.response.mime_type == "application/json":
            print("Intercepted JSON URL:", event.response.url)
            
    page.add_handler(zd.cdp.network.ResponseReceived, log_response)
    await page.send(zd.cdp.network.enable())
    
    print("Searching for milk...")
    results = await search(page, "milk")
    print(f"Got {len(results)} products!")
    for r in results:
        print(r['name'], r['price'])
        
    await browser.stop()

if __name__ == "__main__":
    asyncio.run(main())
