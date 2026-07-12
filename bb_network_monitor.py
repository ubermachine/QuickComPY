import asyncio
import zendriver as zd
import json

async def monitor_network():
    browser = await zd.start(config=zd.Config(sandbox=False, headless=True))
    try:
        page = await browser.get('about:blank', new_tab=True)
        
        # Add network listener
        async def handle_request(event: zd.cdp.network.RequestWillBeSent):
            url = event.request.url
            if event.type_ in ["XHR", "Fetch"]:
                print(f"XHR/FETCH REQUEST: {url}")
                if event.request.has_post_data:
                    print(f"POST DATA: {event.request.post_data}")
                    
        async def handle_response(event: zd.cdp.network.ResponseReceived):
            url = event.response.url
            if event.type_ in ["XHR", "Fetch"]:
                print(f"XHR/FETCH RESPONSE: {url}")
                
        page.add_handler(zd.cdp.network.RequestWillBeSent, handle_request)
        page.add_handler(zd.cdp.network.ResponseReceived, handle_response)
        
        # Run the existing scraper's location setup to capture what it does
        from backend_py.scrapers.bigbasket import set_location
        await set_location(page, "110001")
        
        await asyncio.sleep(3)
        
        # Print cookies to see what was set
        cookies = await page.send(zd.cdp.network.get_cookies())
        print("COOKIES:")
        for c in cookies:
            print(f"{c.name}: {c.value}")
            
    finally:
        await browser.stop()

if __name__ == "__main__":
    asyncio.run(monitor_network())
