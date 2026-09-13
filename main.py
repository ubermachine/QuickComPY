"""QuickCom API layer.

One headless Chromium serves every request, and two costs dominate a search:
the per-platform tab and the scrape behind it. This module attacks both.

  * Tabs are pooled and reused rather than opened per platform per search. A
    fresh target costs a renderer spin-up plus the CDP round trips to install
    the stealth script, enable Network and push the resource blocklist -- paid
    six times on every search under the old create-per-scrape model.
  * Identical concurrent queries collapse onto a single scrape, so two users
    asking for "milk" at the same moment cost one round of traffic, not two.
  * Results stream to the browser per platform as they land, so the user sees
    the first column in a couple of seconds instead of waiting out the slowest
    of six.
  * A search's full ranked pool is returned alongside the visible page of it,
    so re-sorting and filtering happen in the browser with no request at all.
"""

import asyncio
import json
import os
import time
from contextlib import asynccontextmanager

import zendriver as zd
from fastapi import FastAPI, Query
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend_py.registry import BY_KEY, KEYS, PLATFORMS
from backend_py.scrapers import common

# Each platform needs its own tab, and each *loaded* tab is real Chromium
# memory -- see the measurements in the README, which are in gigabytes, not the
# 512MB this once claimed. Four is the measured sweet spot on both peak RSS and
# wall time. The pool size is also the concurrency limit -- a scrape cannot be
# running without holding a tab -- which is why there is no longer a separate
# semaphore to keep in step with it.
MAX_CONCURRENT_TABS = int(os.environ.get("MAX_CONCURRENT_TABS", "4"))

# Product images, fonts and third-party telemetry are never read by a scraper:
# image *URLs* come from the JSON payloads and DOM attributes, never from the
# decoded pixels. Measurement says this does not move peak RSS much (renderer
# process overhead dominates) -- it is on by default because it removes a large
# number of pointless requests per search and shortens page loads. Set
# BLOCK_ASSETS=0 to fetch everything, e.g. when debugging what a page renders.
BLOCK_ASSETS = os.environ.get("BLOCK_ASSETS", "1") != "0"

SEARCH_TIMEOUT = float(os.environ.get("SEARCH_TIMEOUT", "60"))
LOCATION_TIMEOUT = float(os.environ.get("LOCATION_TIMEOUT", "25"))

# Re-sorting or re-filtering a result set must not mean scraping all six
# platforms again -- that is fifteen seconds the user should not pay twice, and
# repeat traffic for the same query is exactly what gets an IP challenged.
SEARCH_CACHE_TTL = float(os.environ.get("SEARCH_CACHE_TTL", "120"))
SEARCH_CACHE_MAX = 32

# A pooled tab parked on about:blank still costs a renderer process. Close the
# ones nothing has asked for in this long, so an idle box drifts back down to
# the browser alone while a busy one keeps its tabs warm.
TAB_IDLE_TTL = float(os.environ.get("TAB_IDLE_TTL", "300"))
TAB_REAP_INTERVAL = 60.0
TAB_RECYCLE_TIMEOUT = 6.0

# query -> (expires_at, {platform_key: ScrapeResult})
_pool_cache = {}

# query -> _Scrape currently running for it, so duplicate requests join in
# rather than starting a second round of traffic at the platforms.
_inflight = {}


def _cache_get(key):
    entry = _pool_cache.get(key)
    if not entry:
        return None
    expires_at, pools = entry
    if time.monotonic() > expires_at:
        _pool_cache.pop(key, None)
        return None
    return pools


def _cache_put(key, pools):
    if len(_pool_cache) >= SEARCH_CACHE_MAX:
        # Cheap eviction: drop whatever expires soonest.
        oldest = min(_pool_cache, key=lambda k: _pool_cache[k][0])
        _pool_cache.pop(oldest, None)
    _pool_cache[key] = (time.monotonic() + SEARCH_CACHE_TTL, pools)


_STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
Object.defineProperty(navigator, 'plugins', { get: () => [1,2,3,4,5] });
Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
window.chrome = { runtime: {} };
Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
"""


# --------------------------------------------------------------------------
# Tab pool
# --------------------------------------------------------------------------

class TabPool:
    """A fixed set of reusable, pre-configured Chromium tabs.

    Opening a tab is not free: a new target costs a renderer spin-up plus three
    CDP round trips (stealth script, Network.enable, the URL blocklist) before
    a scraper can do anything with it. Under create-per-scrape that was paid
    six times per search and thrown away six times per search. The pool pays it
    once per slot instead and hands the same tabs back.

    A semaphore is the concurrency cap -- a scraper that is running is, by
    construction, holding a slot -- and warm tabs are a stack drawn from only
    when there is one. Nothing is opened until a search actually arrives, and
    the stack is popped from the hot end so a box that only ever runs one
    search at a time keeps reusing one tab and lets the rest age out.
    """

    __slots__ = ("_browser", "_size", "_slots", "_warm", "_recycling")

    def __init__(self, browser, size):
        self._browser = browser
        self._size = size
        self._slots = asyncio.Semaphore(size)
        self._warm = []  # (page, released_at), oldest first
        self._recycling = set()

    async def _open(self):
        page = await self._browser.get("about:blank", new_tab=True)
        await page.send(
            zd.cdp.page.add_script_to_evaluate_on_new_document(source=_STEALTH_JS)
        )
        if BLOCK_ASSETS:
            await common.block_heavy_resources(page)
        return page

    @asynccontextmanager
    async def lease(self):
        """Borrow a ready tab, blocking until one is free."""
        await self._slots.acquire()
        page = self._warm.pop()[0] if self._warm else None
        if page is None:
            try:
                page = await self._open()
            except Exception:
                # Hand the slot back or the pool shrinks permanently.
                self._slots.release()
                raise
        try:
            yield page
        finally:
            self._release(page)

    def _release(self, page):
        # Recycling is deliberately off the finishing caller's critical path:
        # blanking the tab must not delay the response it just produced. The
        # task is parked on the pool so it cannot be garbage collected
        # mid-flight, which would strand the slot for the process's lifetime.
        t = asyncio.create_task(self._recycle(page))
        self._recycling.add(t)
        t.add_done_callback(self._recycling.discard)

    async def _recycle(self, page):
        """Return a tab to the pool, blanked and stripped of handlers.

        Blanking drops the site's DOM and JS heap -- the bulk of what a loaded
        product grid costs -- so an idle pool is cheap. Clearing handlers stops
        a scraper that died mid-interception from leaking its CDP callbacks
        into whatever platform borrows the tab next, which under pooling would
        be a correctness bug and not merely a leak.
        """
        try:
            page.remove_handlers()
            await asyncio.wait_for(page.get("about:blank"), timeout=TAB_RECYCLE_TIMEOUT)
        except Exception as e:
            print(f"[pool] discarding tab that would not reset: {type(e).__name__}: {e}")
            try:
                await page.close()
            except Exception:
                pass
            page = None
        if page is not None:
            self._warm.append((page, time.monotonic()))
        # Released last: a waiter that woke before the tab was back would open
        # a second one and quietly grow the pool past its size.
        self._slots.release()

    async def reap(self):
        """Close tabs nothing has borrowed for TAB_IDLE_TTL.

        Keeps the warm-tab win across a burst of searches without holding four
        renderer processes open through the quiet hours between them. Leases
        pop the freshest tab, so the stale ones collect at the front of the
        stack and everything before the first live entry is staler still.
        """
        cutoff = time.monotonic() - TAB_IDLE_TTL
        stale = []
        while self._warm and self._warm[0][1] < cutoff:
            stale.append(self._warm.pop(0)[0])
        for page in stale:
            try:
                await page.close()
            except Exception as e:
                print(f"[pool] error closing idle tab: {type(e).__name__}: {e}")

    async def close(self):
        for t in list(self._recycling):
            t.cancel()
        warm, self._warm = self._warm, []
        for page, _ in warm:
            try:
                await page.close()
            except Exception:
                pass


async def _reap_tabs_forever(pool):
    while True:
        await asyncio.sleep(TAB_REAP_INTERVAL)
        try:
            await pool.reap()
        except Exception as e:
            print(f"[pool] reaper error: {type(e).__name__}: {e}")


# --------------------------------------------------------------------------
# Per-platform work
# --------------------------------------------------------------------------

async def set_loc_svc(pool, key, location):
    print(f"Setting location for {key} to {location}")
    try:
        async with pool.lease() as page:
            ok = await asyncio.wait_for(
                BY_KEY[key].module.set_location(page, location), timeout=LOCATION_TIMEOUT
            )
        return key, bool(ok)
    except Exception as e:
        print(f"Location error {key}: {type(e).__name__} - {e}")
        return key, False


async def search_svc(pool, key, search_term):
    """Search one platform, always returning a structured result.

    Never raises: a platform that is blocked or slow degrades to a status the
    frontend can explain, rather than an empty column indistinguishable from
    "this product does not exist here".
    """
    print(f"Searching {key} for {search_term}")
    started = time.monotonic()
    try:
        async with pool.lease() as page:
            result = await asyncio.wait_for(
                BY_KEY[key].module.search(page, search_term), timeout=SEARCH_TIMEOUT
            )
        if not isinstance(result, common.ScrapeResult):
            # Tolerate a scraper that still returns a bare list.
            products = list(result or [])
            result = common.ScrapeResult(
                products, common.OK if products else common.EMPTY
            )
    except asyncio.TimeoutError:
        print(f"Search timeout {key}")
        result = common.ScrapeResult(
            [], common.TIMEOUT, f"{BY_KEY[key].label} took too long to respond."
        )
    except Exception as e:
        print(f"Search error {key}: {type(e).__name__} - {e}")
        result = common.ScrapeResult([], common.ERROR, f"{type(e).__name__}: {e}")
    print(f"[{key}] finished in {time.monotonic() - started:.1f}s ({result.status})")
    return key, result


class _Scrape:
    """The one scrape of every platform in flight for a given query.

    Holds the per-platform tasks so a streaming client can consume them as they
    land while a plain /api/search client awaits the whole set, and a second
    client asking the same question joins both -- all off a single round of
    traffic at the platforms.
    """

    __slots__ = ("cache_key", "tasks", "all")

    def __init__(self, pool, cache_key, q):
        self.cache_key = cache_key
        self.tasks = {
            svc: asyncio.create_task(search_svc(pool, svc, q)) for svc in KEYS
        }
        self.all = asyncio.ensure_future(self._collect())

    async def _collect(self):
        pools = {}
        for svc, task in self.tasks.items():
            try:
                pools[svc] = (await task)[1]
            except Exception as e:
                print(f"Service {svc} failed with exception: {e}")
                pools[svc] = common.ScrapeResult([], common.ERROR, str(e))
        # Only worth caching if something actually succeeded; caching a round
        # of blocks would keep serving them for the whole TTL.
        if any(p.status == common.OK for p in pools.values()):
            _cache_put(self.cache_key, pools)
        return pools


def _scrape_for(pool, cache_key, q):
    """The in-flight scrape for this query, starting one if there is none."""
    scrape = _inflight.get(cache_key)
    if scrape is not None:
        return scrape
    scrape = _Scrape(pool, cache_key, q)
    _inflight[cache_key] = scrape
    scrape.all.add_done_callback(lambda _t, k=cache_key: _inflight.pop(k, None))
    return scrape


async def _gather_pools(q):
    """Scrape every platform for `q`, or reuse a recent pool for the same query."""
    key = q.strip().lower()
    cached = _cache_get(key)
    if cached is not None:
        print(f"Serving '{q}' from cache")
        return cached

    scrape = _scrape_for(app.state.pool, key, q)
    # Shielded: a client that hangs up must not cancel a scrape other clients
    # are waiting on, and the result is still worth caching for the next one.
    return await asyncio.shield(scrape.all)


async def _stream_pools(q):
    """Yield (platform_key, ScrapeResult) as each platform lands."""
    key = q.strip().lower()
    cached = _cache_get(key)
    if cached is not None:
        print(f"Serving '{q}' from cache")
        for svc in KEYS:
            yield svc, cached[svc]
        return

    scrape = _scrape_for(app.state.pool, key, q)
    pending = set(scrape.tasks.values())
    while pending:
        done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            try:
                svc, result = task.result()
            except Exception as e:
                print(f"Service task failed: {type(e).__name__}: {e}")
                continue
            yield svc, result


# --------------------------------------------------------------------------
# App
# --------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Starting global Zendriver browser...")
    browser_args = [
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
        # Chrome throttles timers and rendering in tabs that are not in front.
        # Every tab we drive is a background tab, so left on, these three
        # actively slow down the concurrent scrapes that are the whole point.
        "--disable-background-timer-throttling",
        "--disable-backgrounding-occluded-windows",
        "--disable-renderer-backgrounding",
        # Site isolation buys nothing when the only pages we load are ones we
        # chose, and costs a renderer process per origin -- the single largest
        # controllable memory line. BackForwardCache likewise retains whole
        # pages we will never navigate back to.
        "--disable-features=site-per-process,IsolateOrigins,BackForwardCache,"
        "TranslateUI,OptimizationHints,MediaRouter,InterestFeedContentSuggestions",
        "--disable-client-side-phishing-detection",
        "--disable-component-update",
        "--disable-domain-reliability",
        "--disable-hang-monitor",
        "--disable-breakpad",
        "--no-default-browser-check",
        "--metrics-recording-only",
        "--mute-audio",
    ]
    if BLOCK_ASSETS:
        # The URL blocklist already stops image *requests*; this stops Blink
        # allocating for them at all, and is the cheaper of the two.
        browser_args.append("--blink-settings=imagesEnabled=false")

    stealth_config = zd.Config(
        sandbox=False,  # Required for Docker/Render
        headless=True,
        browser_args=browser_args,
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36',
        disable_webrtc=True,
    )
    browser = await zd.start(config=stealth_config)
    app.state.browser = browser
    app.state.pool = TabPool(browser, MAX_CONCURRENT_TABS)
    app.state.reaper = asyncio.create_task(_reap_tabs_forever(app.state.pool))
    print(f"Browser started successfully! (pool of {MAX_CONCURRENT_TABS} tabs)")

    yield

    print("Stopping browser...")
    app.state.reaper.cancel()
    await app.state.pool.close()
    await browser.stop()


app = FastAPI(lifespan=lifespan)

# Search payloads are highly repetitive JSON (six columns of product cards),
# which is exactly what gzip is good at -- roughly 8x here. Level 6 rather than
# the default 9: within a percent on this shape of data for a fraction of the
# CPU. Starlette excludes text/event-stream by default, so the streaming
# endpoint below is unaffected.
app.add_middleware(GZipMiddleware, minimum_size=500, compresslevel=6)

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
    """Platform list and branding, so the frontend has no hardcoded copy.

    `maxProducts` rides along because the browser now slices the visible page
    out of the pool itself; without it the page size would be restated in the
    frontend and could drift from the server's.
    """
    # Fixed for the life of the deployment, and fetched on every page load.
    # Letting the browser hold it removes that request from repeat visits.
    return JSONResponse(
        {
            "services": [p.to_dict() for p in PLATFORMS],
            "maxProducts": common.MAX_PRODUCTS,
        },
        headers={"Cache-Control": "public, max-age=300"},
    )


@app.post("/api/set-location")
async def set_location(body: LocationRequest):
    # Cached pools are location-specific; a new pincode makes them wrong.
    _pool_cache.clear()
    pool = app.state.pool
    results = await asyncio.gather(*[
        set_loc_svc(pool, key, body.location) for key in KEYS
    ], return_exceptions=True)

    out = {}
    for key, res in zip(KEYS, results):
        if isinstance(res, Exception):
            print(f"Service {key} failed with exception: {res}")
            out[key] = False
        else:
            out[key] = res[1]
    return out


def _shape(pool, sort, min_discount):
    """Render one platform's pool as the API's per-service object.

    `products` is the visible page; `pool` is every ranked candidate behind it,
    sent so the browser can re-sort and re-filter with no request at all. The
    two overlap, but the overlap is identical text and gzip charges almost
    nothing for it -- far less than a round trip per dropdown change.
    """
    # Build the full filtered set once, then slice -- computing it twice just
    # to count the matches doubled the sort for no reason.
    matched = common.apply_view(
        pool.products, sort=sort, min_discount=min_discount, limit=None,
    )
    view = matched[:common.MAX_PRODUCTS]

    status, message = pool.status, pool.message
    # Distinguish "this platform gave us nothing" from "your filter excluded
    # everything it did give us".
    if not view and pool.products:
        status = common.EMPTY
        message = f"No items at {min_discount}% off or more."

    return {
        "products": view,
        "pool": pool.products,
        "status": status,
        "message": message,
        # How many of the platform's candidates passed the filter, so the UI
        # can say "showing 8 of 23" rather than implying there were 8.
        "matched": len(matched),
    }


_SORT_PATTERN = "^(relevance|discount)$"


@app.get("/api/search")
async def search(
    q: str,
    sort: str = Query(common.SORT_RELEVANCE, pattern=_SORT_PATTERN),
    min_discount: int = Query(0, ge=0, le=99),
):
    """Search every platform, answering once all six have landed.

    `sort` and `min_discount` shape the view only -- the underlying scrape is
    identical, so the default call behaves exactly as it always has. Prefer
    /api/search/stream for interactive use: same data, first column in a
    fraction of the time.
    """
    pools = await _gather_pools(q)
    return {svc: _shape(pools[svc], sort, min_discount) for svc in KEYS}


def _sse(event, payload):
    return f"event: {event}\ndata: {json.dumps(payload, separators=(',', ':'))}\n\n"


@app.get("/api/search/stream")
async def search_stream(
    q: str,
    sort: str = Query(common.SORT_RELEVANCE, pattern=_SORT_PATTERN),
    min_discount: int = Query(0, ge=0, le=99),
):
    """The same search, streamed a column at a time as Server-Sent Events.

    A search is only ever as fast as its slowest platform, and the slowest is
    routinely three times the fastest. Waiting for all six before showing any
    means every user pays the worst case; streaming means they pay it only for
    the one column that earned it.
    """
    async def events():
        started = time.monotonic()
        served = 0
        try:
            async for svc, pool in _stream_pools(q):
                payload = _shape(pool, sort, min_discount)
                payload["service"] = svc
                served += 1
                yield _sse("result", payload)
        except Exception as e:
            print(f"Stream error: {type(e).__name__}: {e}")
            yield _sse("error", {"message": f"{type(e).__name__}: {e}"})
        yield _sse("done", {
            "served": served,
            "elapsed": round(time.monotonic() - started, 2),
        })

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            # Tell any reverse proxy in front of us not to buffer, which would
            # undo the streaming entirely.
            "X-Accel-Buffering": "no",
        },
    )


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
