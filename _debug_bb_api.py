import asyncio
import json
import urllib.parse
import zendriver as zd
from backend_py.scrapers.bigbasket import set_location

async def main():
    browser = await zd.start(config=zd.Config(headless=True, disable_webrtc=True))
    try:
        page = await browser.get('about:blank', new_tab=True)
        await page.send(zd.cdp.network.enable())
        
        await set_location(page, "201306")
        
        target_requests = set()
        responses = []

        async def handle_response(event: zd.cdp.network.ResponseReceived):
            if "listing-svc/v2/products" in event.response.url and event.response.mime_type == "application/json":
                print("Found JSON API:", event.response.url)
                target_requests.add(event.request_id)

        async def handle_loading(event: zd.cdp.network.LoadingFinished):
            if event.request_id in target_requests:
                try:
                    body = await page.send(zd.cdp.network.get_response_body(request_id=event.request_id))
                    responses.append(body[0])
                    print(f"Captured body of length: {len(body[0])}")
                except Exception as e:
                    print(f"Error: {e}")

        page.add_handler(zd.cdp.network.ResponseReceived, handle_response)
        page.add_handler(zd.cdp.network.LoadingFinished, handle_loading)
        
        await page.get("https://www.bigbasket.com/ps/?q=eggs")
        await asyncio.sleep(8)
        
        if responses:
            with open("bb_api_dump.json", "w", encoding="utf-8") as f:
                f.write(responses[0])
                print("Dumped to bb_api_dump.json")
    finally:
        await browser.stop()

if __name__ == "__main__":
    asyncio.run(main())
