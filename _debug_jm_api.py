import asyncio
import json
import zendriver as zd

async def main():
    browser = await zd.start(config=zd.Config(headless=True, disable_webrtc=True))
    try:
        page = await browser.get('about:blank', new_tab=True)
        await page.send(zd.cdp.network.enable())
        
        target_requests = set()
        responses = []

        async def handle_response(event: zd.cdp.network.ResponseReceived):
            if "jiomart.com" in event.response.url and event.response.mime_type == "application/json":
                print("Found JSON API:", event.response.url)
                target_requests.add(event.request_id)

        async def handle_loading(event: zd.cdp.network.LoadingFinished):
            if event.request_id in target_requests:
                try:
                    body = await page.send(zd.cdp.network.get_response_body(request_id=event.request_id))
                    responses.append(body[0])
                    print(f"Captured body of length: {len(body[0])}")
                except Exception as e:
                    pass

        page.add_handler(zd.cdp.network.ResponseReceived, handle_response)
        page.add_handler(zd.cdp.network.LoadingFinished, handle_loading)
        
        await page.get("https://www.jiomart.com/products?q=eggs")
        await asyncio.sleep(8)
        
        # Save all responses to check
        for i, r in enumerate(responses):
            try:
                data = json.loads(r)
                with open(f"jm_api_dump_{i}.json", "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
            except Exception:
                pass
        print(f"Dumped {len(responses)} files")
    finally:
        await browser.stop()

if __name__ == "__main__":
    asyncio.run(main())
