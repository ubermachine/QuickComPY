import asyncio
import json
import uuid
import sys
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import zendriver as zd
import traceback

from backend_py.scrapers import blinkit, bigbasket, jiomart, zepto, instamart

app = FastAPI()

SERVICES = ["blinkit", "bigbasket", "jiomart", "zepto", "instamart"]
SCRAPERS = {
    "blinkit": blinkit,
    "bigbasket": bigbasket,
    "jiomart": jiomart,
    "zepto": zepto,
    "instamart": instamart
}

# --- Single Global Browser Context ---
global_browser = None

async def init_browser():
    global global_browser
    print("Starting Zendriver global browser...")
    global_browser = await zd.start(config=zd.Config(sandbox=False, headless=True))
    print("Zendriver started.")

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(init_browser())

@app.websocket("/")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    client_id = websocket.query_params.get("clientId", str(uuid.uuid4()))
    print(f"Client connected: {client_id}")

    # Wait for browser to be initialized
    while not global_browser:
        await asyncio.sleep(0.5)

    try:
        while True:
            data_str = await websocket.receive_text()
            data = json.loads(data_str)
            action = data.get("action")

            if action == "setLocation":
                location = data.get("location")
                print(f"Setting location {location} for {client_id}")

                async def set_loc_svc(svc):
                    page = await global_browser.get('about:blank', new_tab=True)
                    try:
                        success = await SCRAPERS[svc].set_location(page, location)
                        return svc, success
                    except Exception as e:
                        print(f"Location error {svc}: {e}")
                        return svc, False
                    finally:
                        await page.close()

                results = await asyncio.gather(*[set_loc_svc(s) for s in SERVICES])

                await websocket.send_json({
                    "action": "setLocation",
                    "status": "success",
                    "location": location,
                    "message": "Location set successfully",
                    "details": dict(results)
                })

            elif action == "search":
                search_term = data.get("searchTerm")
                print(f"Searching {search_term} for {client_id}")

                await websocket.send_json({
                    "action": "statusUpdate",
                    "step": "search",
                    "status": "started",
                    "message": f"Starting search for {search_term}"
                })

                async def search_svc(svc):
                    page = await global_browser.get('about:blank', new_tab=True)
                    try:
                        await websocket.send_json({
                            "action": "statusUpdate",
                            "step": "search",
                            "status": "progress",
                            "message": f"Searching {svc}..."
                        })
                        products = await SCRAPERS[svc].search(page, search_term)
                        return svc, products
                    except Exception as e:
                        print(f"Search error {svc}: {e}")
                        traceback.print_exc()
                        return svc, []
                    finally:
                        await page.close()

                results = await asyncio.gather(*[search_svc(s) for s in SERVICES])

                all_products = {}
                total = 0
                for svc, prods in results:
                    all_products[svc] = prods
                    total += len(prods)

                await websocket.send_json({
                    "action": "searchResults",
                    "status": "success",
                    "products": all_products,
                    "productCount": {"total": total}
                })

                await websocket.send_json({
                    "action": "statusUpdate",
                    "step": "search",
                    "status": "completed",
                    "message": "Search completed"
                })

    except WebSocketDisconnect:
        print(f"Client disconnected: {client_id}")
    except Exception as e:
        print(f"Websocket error: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)
