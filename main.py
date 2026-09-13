"""QuickCom API layer.

One headless Chromium serves every request, and the scrape behind each
platform is the cost that dominates a search. This module pays it as rarely,
and shows it as early, as it can.

  * Every scrape gets a fresh tab, at most MAX_CONCURRENT_TABS open at once.
    Reusing tabs saved ~33ms apiece but carried one platform's page state into
    the next, which broke Zepto against the live site -- see TabPool.
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

# How long a finished tab gets to close. Its slot is only handed on once it
# has, so a close that hangs must not be allowed to strand the slot.
TAB_CLOSE_TIMEOUT = 6.0

# query -> (expires_at, {platform_key: ScrapeResult})
_pool_cache = {}

# query -> _Scrape currently running for it, so duplicate requests join in
# rather than starting a second round of traffic at the platforms.
_inflight = {}

# Bumped whenever the delivery location changes. A scrape's prices belong to
# the location that was set when it started, so one that straddles a change
# must neither be cached nor joined by a search made after it.
_location_epoch = 0


def _invalidate_searches():
    """Forget every result, and every scrape in flight, for the old location."""
    global _location_epoch
    _location_epoch += 1
    _pool_cache.clear()
    # Detached rather than cancelled: clients already waiting on those scrapes
    # still get their answer, but nobody new joins them.
    _inflight.clear()


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
    """A cap on how many Chromium tabs are open at once, each one fresh.

    Every lease opens a new tab and closes it on release. Tabs were briefly
    reused instead -- blanked to about:blank between leases -- to skip the
    setup cost of a new target, measured at a median of 33ms. It was not worth
    it. A tab carries state across navigations that blanking does not clear:
    sessionStorage for every origin it has visited, and CDP overrides such as
    the geolocation Instamart's set_location installs. Against the live sites,
    with reuse Zepto loaded its search page and then never booted on about half
    of all searches -- an empty body and no API call -- and with a fresh tab
    per lease it went 8 for 8. Which piece of carried state trips it was not
    isolated; carrying none is what measured clean.

    The semaphore is the concurrency cap, and a slot is only handed on once the
    previous tab has actually closed, so the browser never holds more than
    `size` tabs.
    """

    __slots__ = ("_browser", "_slots", "_closing")

    def __init__(self, browser, size):
        self._browser = browser
        self._slots = asyncio.Semaphore(size)
        self._closing = set()

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
        """Borrow a fresh, configured tab, blocking until a slot is free."""
        await self._slots.acquire()
        try:
            page = await self._open()
        except BaseException:
            # Hand the slot back or the pool shrinks permanently.
            self._slots.release()
            raise
        try:
            yield page
        finally:
            self._release(page)

    def _release(self, page):
        # Closing is deliberately off the finishing caller's critical path: it
        # must not delay the response the tab just produced. The task is parked
        # on the pool so it cannot be garbage collected mid-flight, which would
        # strand the slot for the process's lifetime.
        t = asyncio.create_task(self._close(page))
        self._closing.add(t)
        t.add_done_callback(self._closing.discard)

    async def _close(self, page):
        try:
            await asyncio.wait_for(page.close(), timeout=TAB_CLOSE_TIMEOUT)
        except Exception as e:
            print(f"[pool] error closing tab: {type(e).__name__}: {e}")
        finally:
            # Released last: a waiter woken before the tab was gone would open
            # another and briefly run the browser past its cap.
            self._slots.release()

    async def close(self):
        for t in list(self._closing):
            t.cancel()


# --------------------------------------------------------------------------
# Per-platform work
# --------------------------------------------------------------------------

# Observed scrape time per platform, as an exponential moving average.
#
# While the pool is smaller than the number of platforms, the order tasks queue
# in *is* scheduling policy: the platforms that start last decide when the
# search finishes. Starting the slowest first is the longest-processing-time
# rule, and it shortens the tail directly -- registry order currently starts
# Amazon last, and Amazon is the slowest of the six.
_DURATIONS = {}
_DURATION_ALPHA = 0.3


def _record_duration(key, seconds):
    previous = _DURATIONS.get(key)
    _DURATIONS[key] = (
        seconds if previous is None
        else previous + _DURATION_ALPHA * (seconds - previous)
    )


def _scrape_order():
    """Platform keys, slowest first by what we have actually measured.

    A platform nobody has timed yet sorts first: finding out early that it is
    expensive costs nothing, whereas keeping an expensive one at the back of
    the queue costs its full duration on every search.
    """
    return sorted(KEYS, key=lambda k: -_DURATIONS.get(k, float("inf")))


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
    queued_at = time.monotonic()
    started = None
    try:
        async with pool.lease() as page:
            # Timed from the lease rather than the call: waiting for a slot is
            # queueing, and folding that in would make a platform look slow for
            # having been scheduled late -- the very thing the estimate exists
            # to fix, feeding itself.
            started = time.monotonic()
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

    now = time.monotonic()
    if started is not None:
        _record_duration(key, now - started)
        print(f"[{key}] finished in {now - queued_at:.1f}s "
              f"({now - started:.1f}s scraping) ({result.status})")
    else:
        print(f"[{key}] never got a tab after {now - queued_at:.1f}s ({result.status})")
    return key, result


class _Scrape:
    """The one scrape of every platform in flight for a given query.

    Holds the per-platform tasks so a streaming client can consume them as they
    land while a plain /api/search client awaits the whole set, and a second
    client asking the same question joins both -- all off a single round of
    traffic at the platforms.
    """

    __slots__ = ("cache_key", "epoch", "tasks", "all")

    def __init__(self, pool, cache_key, q):
        self.cache_key = cache_key
        self.epoch = _location_epoch
        # Created slowest-first: see _scrape_order.
        self.tasks = {
            svc: asyncio.create_task(search_svc(pool, svc, q))
            for svc in _scrape_order()
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
        # of blocks would keep serving them for the whole TTL. And only if the
        # location did not change underneath it, or these prices are wrong.
        if (self.epoch == _location_epoch
                and any(p.status == common.OK for p in pools.values())):
            _cache_put(self.cache_key, pools)
        return pools


def _scrape_for(pool, cache_key, q):
    """The in-flight scrape for this query, starting one if there is none."""
    scrape = _inflight.get(cache_key)
    if scrape is not None:
        return scrape
    scrape = _Scrape(pool, cache_key, q)
    _inflight[cache_key] = scrape

    def forget(_task):
        # Only if the entry is still ours: a location change may have replaced
        # it with a scrape for the new location, which must stay joinable.
        if _inflight.get(cache_key) is scrape:
            del _inflight[cache_key]

    scrape.all.add_done_callback(forget)
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
    print(f"Browser started successfully! (up to {MAX_CONCURRENT_TABS} tabs at once)")

    yield

    print("Stopping browser...")
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
    # Cached pools and in-flight scrapes are location-specific; a new pincode
    # makes them wrong. Invalidated on both sides of the change: before, so no
    # new search joins a scrape for the old location, and after, so nothing
    # scraped while the platforms were half-moved gets cached.
    _invalidate_searches()
    pool = app.state.pool
    results = await asyncio.gather(*[
        set_loc_svc(pool, key, body.location) for key in KEYS
    ], return_exceptions=True)
    _invalidate_searches()

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
