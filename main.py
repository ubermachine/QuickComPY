import asyncio
import os
from contextlib import asynccontextmanager

import zendriver as zd
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend_py.registry import BY_KEY, KEYS, PLATFORMS
from backend_py.scrapers import common

# Each platform needs its own tab, and each tab is real Chromium memory. Five
# at once fits a 512MB box; the cap keeps that true as platforms are added.
MAX_CONCURRENT_TABS = int(os.environ.get("MAX_CONCURRENT_TABS", "4"))

SEARCH_TIMEOUT = float(os.environ.get("SEARCH_TIMEOUT", "60"))
LOCATION_TIMEOUT = float(os.environ.get("LOCATION_TIMEOUT", "25"))

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
    """Close a tab without blocking the response on it.

    The task is parked on the loop so it is not garbage collected mid-flight,
    which would leak the tab.
    """
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


async def set_loc_svc(browser, key, location, sem):
    async with sem:
        print(f"Setting location for {key} to {location}")
        page = None
        try:
            page = await stealth_new_page(browser)
            ok = await asyncio.wait_for(
                BY_KEY[key].module.set_location(page, location), timeout=LOCATION_TIMEOUT
            )
            return key, bool(ok)
        except Exception as e:
            print(f"Location error {key}: {type(e).__name__} - {e}")
            return key, False
        finally:
            if page:
                robust_close(page, asyncio.get_running_loop())


async def search_svc(browser, key, search_term, sem):
    """Search one platform, always returning a structured result.

    Never raises: a platform that is blocked or slow degrades to a status the
    frontend can explain, rather than an empty column indistinguishable from
    "this product does not exist here".
    """
    async with sem:
        print(f"Searching {key} for {search_term}")
        page = None
        try:
            page = await stealth_new_page(browser)
            result = await asyncio.wait_for(
                BY_KEY[key].module.search(page, search_term), timeout=SEARCH_TIMEOUT
            )
            if isinstance(result, common.ScrapeResult):
                return key, result
            # Tolerate a scraper that still returns a bare list.
            products = list(result or [])
            return key, common.ScrapeResult(
                products, common.OK if products else common.EMPTY
            )
        except asyncio.TimeoutError:
            print(f"Search timeout {key}")
            return key, common.ScrapeResult(
                [], common.TIMEOUT, f"{BY_KEY[key].label} took too long to respond."
            )
        except Exception as e:
            print(f"Search error {key}: {type(e).__name__} - {e}")
            return key, common.ScrapeResult(
                [], common.ERROR, f"{type(e).__name__}: {e}"
            )
        finally:
            if page:
                robust_close(page, asyncio.get_running_loop())


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Starting global Zendriver browser...")
    stealth_config = zd.Config(
        sandbox=False,  # Required for Docker/Render
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
    app.state.sem = asyncio.Semaphore(MAX_CONCURRENT_TABS)
    print(f"Browser started successfully! (max {MAX_CONCURRENT_TABS} concurrent tabs)")

    yield

    print("Stopping browser...")
    await browser.stop()


app = FastAPI(lifespan=lifespan)

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


@app.get("/api/services")
async def services():
    """Platform list and branding, so the frontend has no hardcoded copy."""
    return {"services": [p.to_dict() for p in PLATFORMS]}


@app.post("/api/set-location")
async def set_location(body: LocationRequest):
    sem = app.state.sem
    results = await asyncio.gather(*[
        set_loc_svc(app.state.browser, key, body.location, sem) for key in KEYS
    ], return_exceptions=True)

    out = {}
    for key, res in zip(KEYS, results):
        if isinstance(res, Exception):
            print(f"Service {key} failed with exception: {res}")
            out[key] = False
        else:
            out[key] = res[1]
    return out


@app.get("/api/search")
async def search(q: str):
    sem = app.state.sem
    results = await asyncio.gather(*[
        search_svc(app.state.browser, key, q, sem) for key in KEYS
    ], return_exceptions=True)

    out = {}
    for key, res in zip(KEYS, results):
        if isinstance(res, Exception):
            print(f"Service {key} failed with exception: {res}")
            out[key] = common.ScrapeResult([], common.ERROR, str(res)).to_dict()
        else:
            out[key] = res[1].to_dict()
    return out


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
