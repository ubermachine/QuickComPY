"""Dump the full Swiggy Instamart search API response to understand product structure."""
import asyncio
import json
import zendriver as zd

async def main():
    config = zd.Config(headless=True, sandbox=False)
    browser = await zd.start(config=config)
    page = await browser.get('about:blank', new_tab=True)

    await page.get("https://www.swiggy.com/instamart")
    await asyncio.sleep(3)

    # Set location
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

    collected = {"done": False, "body": None}
    target_ids = set()

    async def on_response(event):
        if collected["done"]: return
        if "api/instamart/search" in event.response.url:
            target_ids.add(event.request_id)
            print(f"[+] Matched search API: {event.response.url[:120]}")

    async def on_loading_finished(event):
        if collected["done"]: return
        if event.request_id not in target_ids: return
        try:
            body_info = await page.send(zd.cdp.network.get_response_body(request_id=event.request_id))
            if body_info:
                data = json.loads(body_info[0])
                collected["body"] = data
                collected["done"] = True
        except Exception as e:
            print(f"[!] Error getting body: {e}")

    await page.send(zd.cdp.network.enable())
    page.add_handler(zd.cdp.network.ResponseReceived, on_response)
    page.add_handler(zd.cdp.network.LoadingFinished, on_loading_finished)

    await page.get("https://www.swiggy.com/instamart/search?query=milk")
    
    for _ in range(150):
        if collected["done"]: break
        await asyncio.sleep(0.1)

    if collected["body"]:
        with open("im_api_dump.json", "w", encoding="utf-8") as f:
            json.dump(collected["body"], f, indent=2, ensure_ascii=False)
        
        data = collected["body"].get("data", {})
        cards = data.get("cards", [])
        print(f"\nTotal cards: {len(cards)}")
        for i, card in enumerate(cards[:5]):
            print(f"\n--- Card {i} ---")
            print(f"  Keys: {list(card.keys())}")
            if "data" in card:
                print(f"  card.data keys: {list(card['data'].keys()) if isinstance(card['data'], dict) else type(card['data'])}")
    else:
        print("[!] No search API response intercepted")

    await browser.stop()

if __name__ == "__main__":
    asyncio.run(main())
