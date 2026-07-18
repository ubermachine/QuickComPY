import asyncio
import zendriver as zd
import urllib.parse
from backend_py.scrapers.zepto import inject_location_cookies, resolve_coords

async def main():
    config = zd.Config(headless=True, disable_webrtc=True, user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36')
    browser = await zd.start(config=config)
    try:
        page = await browser.get('about:blank', new_tab=True)
        # Apply stealth
        await page.send(zd.cdp.page.add_script_to_evaluate_on_new_document(source="""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        """))
        
        # Intercept network
        await page.send(zd.cdp.network.enable())
        
        # Create a queue to hold intercepted data
        api_responses = []
        
        async def on_response_received(event):
            try:
                resp = event.response
                url = resp.url
                if 'api' in url.lower() and ('search' in url.lower() or 'catalog' in url.lower() or 'graphql' in url.lower()):
                    if resp.mime_type == 'application/json':
                        print(f"Intercepted API: {url}")
                        body_info = await page.send(zd.cdp.network.get_response_body(request_id=event.request_id))
                        if body_info:
                            api_responses.append({'url': url, 'body': body_info[0][:2000]})
                            if 'search' in url.lower() and not url.endswith('filters'):
                                with open("zepto_api_debug.json", "w", encoding="utf-8") as f:
                                    f.write(body_info[0])
            except Exception as e:
                print(f"Error intercepting response: {e}")
                
        page.add_handler(zd.cdp.network.ResponseReceived, on_response_received)
        
        # Navigate and set cookies
        await page.get("https://www.zepto.com/")
        await asyncio.sleep(2)
        
        coords = resolve_coords('201301')
        await inject_location_cookies(page, '201301', str(coords['lat']), str(coords['lon']))
        
        await page.get("https://www.zepto.com/search?query=milk")
        await asyncio.sleep(6)
        
        print(f"Total intercepted: {len(api_responses)}")
        for r in api_responses:
            print(f"URL: {r['url']}")
            print(f"BODY PREFIX: {r['body']}\n")
            
        # Let's also grab HTML to see if they changed classes
        h = await page.get_content()
        with open("zepto_debug_dom.html", "w", encoding="utf-8") as f:
            f.write(h)
            
    finally:
        await browser.stop()

if __name__ == "__main__":
    asyncio.run(main())
