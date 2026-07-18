"""Discover Swiggy Instamart's internal search API by intercepting network responses."""
import asyncio
import json
import zendriver as zd

async def main():
    config = zd.Config(headless=False, sandbox=False)
    browser = await zd.start(config=config)
    page = await browser.get('about:blank', new_tab=True)

    # Inject location into localStorage before navigating
    await page.get("https://www.swiggy.com/instamart")
    await asyncio.sleep(3)

    # Check for WAF
    html = await page.get_content()
    if "AwsWafIntegration" in html or "challenge-container" in html:
        print("[!] WAF challenge detected on initial load!")
        print("[!] Waiting 10s for auto-solve...")
        await asyncio.sleep(10)
        html = await page.get_content()
        if "AwsWafIntegration" in html:
            print("[!] WAF still present after wait")
        else:
            print("[+] WAF resolved!")

    # Set location via localStorage
    await page.evaluate("""
    (() => {
        const locationData = {
            lat: 28.5147, lng: 77.4855,
            address: 'Noida, Uttar Pradesh, India',
            area: 'Noida', city: 'Uttar Pradesh',
            areaId: '', latlng: '28.5147,77.4855'
        };
        localStorage.setItem('userLocation', JSON.stringify(locationData));
        localStorage.setItem('swiggy_location', JSON.stringify(locationData));
        localStorage.setItem('IM_location', JSON.stringify(locationData));
    })()
    """)

    # Now enable network interception and navigate to search
    intercepted = []

    async def on_response(event):
        url = event.response.url
        mime = event.response.mime_type
        if mime and "json" in mime:
            print(f"[JSON] {url[:150]}")
            intercepted.append({"url": url, "request_id": event.request_id, "status": event.response.status})

    async def on_loading_finished(event):
        for item in intercepted:
            if item["request_id"] == event.request_id:
                try:
                    body_info = await page.send(zd.cdp.network.get_response_body(request_id=event.request_id))
                    if body_info:
                        data = json.loads(body_info[0])
                        # Look for product-like structures
                        data_str = json.dumps(data)
                        if "product" in data_str.lower() or "widget" in data_str.lower() or "item" in data_str.lower():
                            print(f"\n[PRODUCT DATA FOUND] URL: {item['url'][:150]}")
                            # Print top-level keys
                            if isinstance(data, dict):
                                print(f"  Top-level keys: {list(data.keys())}")
                                # Dig deeper
                                for k, v in data.items():
                                    if isinstance(v, dict):
                                        print(f"  {k} -> keys: {list(v.keys())[:10]}")
                                    elif isinstance(v, list):
                                        print(f"  {k} -> list of {len(v)} items")
                except Exception as e:
                    pass

    await page.send(zd.cdp.network.enable())
    page.add_handler(zd.cdp.network.ResponseReceived, on_response)
    page.add_handler(zd.cdp.network.LoadingFinished, on_loading_finished)

    print("\n--- Navigating to search page for 'milk' ---\n")
    await page.get("https://www.swiggy.com/instamart/search?query=milk")
    await asyncio.sleep(10)

    print(f"\n--- Total JSON responses intercepted: {len(intercepted)} ---")
    for item in intercepted:
        print(f"  {item['url'][:120]}")

    await browser.stop()

if __name__ == "__main__":
    asyncio.run(main())
