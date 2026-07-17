import os
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import zendriver as zd

from backend_py.scrapers import blinkit, bigbasket, jiomart, zepto

SERVICES = ["blinkit", "bigbasket", "jiomart", "zepto"]
SCRAPERS = {
    "blinkit": blinkit,
    "bigbasket": bigbasket,
    "jiomart": jiomart,
    "zepto": zepto,
}

_STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
Object.defineProperty(navigator, 'plugins', { get: () => [1,2,3,4,5] });
Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
window.chrome = { runtime: {} };
Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
"""

async def stealth_new_page(browser):
    page = await browser.get('about:blank', new_tab=True)
    await page.send(zd.cdp.page.add_script_to_evaluate_on_new_document(source=_STEALTH_JS))
    return page

def robust_close(page, loop):
    async def _close():
        try:
            await page.close()
        except Exception as e:
            print(f"Error closing page: {e}")
    t = asyncio.create_task(_close())
    if not hasattr(loop, 'cleanup_tasks'):
        loop.cleanup_tasks = set()
    loop.cleanup_tasks.add(t)
    t.add_done_callback(loop.cleanup_tasks.discard)

async def set_loc_svc(browser, svc, location):
    print(f"Setting location for {svc} to {location}")
    page = None
    try:
        page = await stealth_new_page(browser)
        success = await asyncio.wait_for(SCRAPERS[svc].set_location(page, location), timeout=15.0)
        return svc, success
    except Exception as e:
        print(f"Location error {svc}: {type(e).__name__} - {e}")
        return svc, False
    finally:
        if page:
            robust_close(page, asyncio.get_running_loop())

async def search_svc(browser, svc, search_term):
    print(f"Searching {svc} for {search_term}")
    page = None
    try:
        page = await stealth_new_page(browser)
        products = await asyncio.wait_for(SCRAPERS[svc].search(page, search_term), timeout=45.0)
        return svc, products
    except Exception as e:
        print(f"Search error {svc}: {type(e).__name__} - {e}")
        return svc, []
    finally:
        if page:
            robust_close(page, asyncio.get_running_loop())

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Starting global Zendriver browser...")
    stealth_config = zd.Config(
        sandbox=False, # Required for Docker/Render
        headless=True,
        browser_args=[
            "--disable-gpu",
            "--disable-dev-shm-usage",
            "--disable-software-rasterizer",
            "--no-first-run",
            "--no-zygote",
            "--disable-extensions",
            "--disable-background-networking",
            "--disable-default-apps",
            "--disable-sync",
            "--disable-translate",
            "--js-flags=--max-old-space-size=256",
        ],
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36',
        disable_webrtc=True,
    )
    browser = await zd.start(config=stealth_config)
    app.state.browser = browser
    print("Browser started successfully!")
    
    yield
    
    print("Stopping browser...")
    await browser.stop()

app = FastAPI(lifespan=lifespan)

# Mount static files correctly
os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

class LocationRequest(BaseModel):
    location: str

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/")
async def index():
    return FileResponse("static/index.html")

@app.post("/api/set-location")
async def set_location(body: LocationRequest):
    browser = app.state.browser
    results = await asyncio.gather(*[
        set_loc_svc(browser, svc, body.location) for svc in SERVICES
    ], return_exceptions=True)
    
    results_dict = {}
    for i, svc in enumerate(SERVICES):
        res = results[i]
        if isinstance(res, Exception):
            print(f"Service {svc} failed with exception: {res}")
            results_dict[svc] = False
        else:
            results_dict[svc] = res[1]
    return results_dict

@app.get("/api/search")
async def search(q: str):
    browser = app.state.browser
    results = await asyncio.gather(*[
        search_svc(browser, svc, q) for svc in SERVICES
    ], return_exceptions=True)
    
    results_dict = {}
    for i, svc in enumerate(SERVICES):
        res = results[i]
        if isinstance(res, Exception):
            print(f"Service {svc} failed with exception: {res}")
            results_dict[svc] = []
        else:
            results_dict[svc] = res[1]
    return results_dict

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
