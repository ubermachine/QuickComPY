"""Tests for the API layer in main.py -- tab pooling, caching, single-flight
and the streaming search endpoint.

No browser is started: the pool is driven against a fake browser whose tabs
record what was done to them, and platform scrapers are stubbed through the
registry. Everything here is about the machinery around a scrape, not a scrape.
"""

import asyncio
import json
import os
import sys

_project_root = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import pytest

import main
from backend_py.scrapers import common


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

class FakePage:
    def __init__(self, tab_id):
        self.tab_id = tab_id
        self.url = "about:blank"
        self.navigations = []
        self.handler_clears = 0
        self.closed = False
        self.reset_fails = False

    def remove_handlers(self, event_type=None, handler=None):
        self.handler_clears += 1

    async def get(self, url, **kwargs):
        if self.reset_fails and url == "about:blank":
            raise RuntimeError("renderer gone")
        self.navigations.append(url)
        self.url = url
        return self

    async def send(self, *args, **kwargs):
        return None

    async def close(self):
        self.closed = True


class FakeBrowser:
    def __init__(self):
        self.tabs = []

    async def get(self, url, new_tab=False):
        page = FakePage(len(self.tabs))
        self.tabs.append(page)
        return page


class StubModule:
    """Stands in for a scraper module in the registry."""

    def __init__(self, result=None, delay=0.0, raises=None, loc_ok=True):
        self.result = result if result is not None else common.ScrapeResult([], common.EMPTY)
        self.delay = delay
        self.raises = raises
        self.loc_ok = loc_ok
        self.calls = 0
        self.pages = []

    async def search(self, page, term):
        self.calls += 1
        self.pages.append(page)
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.raises:
            raise self.raises
        return self.result

    async def set_location(self, page, location):
        self.calls += 1
        return self.loc_ok


def product(name, price, mrp=None):
    p = {"id": f"id_{name}", "name": name, "price": price, "originalPrice": mrp}
    p["discountPercent"] = common.discount_percent(p)
    return p


@pytest.fixture
def clean_state():
    """Each test gets an empty cache, no in-flight scrapes, no timing history."""
    for store in (main._pool_cache, main._inflight, main._DURATIONS):
        store.clear()
    yield
    for store in (main._pool_cache, main._inflight, main._DURATIONS):
        store.clear()


@pytest.fixture
def stub_platforms(clean_state):
    """Swap every registry module for a stub, restoring the real ones after."""
    originals = {k: main.BY_KEY[k].module for k in main.KEYS}
    stubs = {}
    for k in main.KEYS:
        stubs[k] = StubModule(common.ScrapeResult([product(f"{k} milk", "10")], common.OK))
        main.BY_KEY[k].module = stubs[k]
    yield stubs
    for k, mod in originals.items():
        main.BY_KEY[k].module = mod


# ---------------------------------------------------------------------------
# TabPool
# ---------------------------------------------------------------------------

async def test_pool_opens_lazily_and_reuses_the_same_tab():
    browser = FakeBrowser()
    pool = main.TabPool(browser, 2)
    assert browser.tabs == [], "a pool must cost nothing until something leases"

    async with pool.lease() as page:
        first = page
    # The recycle happens off the critical path; let it land.
    for _ in range(5):
        await asyncio.sleep(0)

    async with pool.lease() as page:
        assert page is first, "the second lease should reuse the warm tab"
    assert len(browser.tabs) == 1


async def test_pool_caps_concurrency_at_its_size():
    browser = FakeBrowser()
    pool = main.TabPool(browser, 2)
    live = 0
    peak = 0

    async def worker():
        nonlocal live, peak
        async with pool.lease():
            live += 1
            peak = max(peak, live)
            await asyncio.sleep(0.02)
            live -= 1

    await asyncio.gather(*[worker() for _ in range(6)])
    assert peak == 2
    assert len(browser.tabs) == 2, "six scrapes should not have opened six tabs"


async def test_recycled_tab_is_blanked_and_stripped_of_handlers():
    browser = FakeBrowser()
    pool = main.TabPool(browser, 1)
    async with pool.lease() as page:
        await page.get("https://example.com/search")
    for _ in range(5):
        await asyncio.sleep(0)

    page = browser.tabs[0]
    assert page.navigations[-1] == "about:blank", "a released tab must not keep the site loaded"
    assert page.handler_clears >= 1, "stale CDP handlers would leak into the next platform"


async def test_tab_that_will_not_reset_is_discarded_not_handed_back():
    browser = FakeBrowser()
    pool = main.TabPool(browser, 1)
    async with pool.lease() as page:
        page.reset_fails = True
    for _ in range(5):
        await asyncio.sleep(0)

    assert browser.tabs[0].closed is True
    async with pool.lease() as page:
        assert page is not browser.tabs[0], "a tab we could not reset must be replaced"
    assert len(browser.tabs) == 2


async def test_failed_open_returns_the_slot_to_the_pool():
    class BrokenBrowser(FakeBrowser):
        def __init__(self):
            super().__init__()
            self.attempts = 0

        async def get(self, url, new_tab=False):
            self.attempts += 1
            if self.attempts == 1:
                raise RuntimeError("out of memory")
            return await super().get(url, new_tab=new_tab)

    browser = BrokenBrowser()
    pool = main.TabPool(browser, 1)
    with pytest.raises(RuntimeError):
        async with pool.lease():
            pass
    # A lost slot would deadlock every later search, so this must still work.
    async with pool.lease() as page:
        assert page is not None


async def test_reap_closes_idle_tabs_but_keeps_fresh_ones(monkeypatch):
    browser = FakeBrowser()
    pool = main.TabPool(browser, 2)
    async with pool.lease():
        pass
    for _ in range(5):
        await asyncio.sleep(0)

    monkeypatch.setattr(main, "TAB_IDLE_TTL", 1000.0)
    await pool.reap()
    assert browser.tabs[0].closed is False, "a freshly used tab must survive the sweep"

    monkeypatch.setattr(main, "TAB_IDLE_TTL", -1.0)
    await pool.reap()
    assert browser.tabs[0].closed is True

    # Capacity must survive the reap, or the pool shrinks every sweep.
    async with pool.lease() as page:
        assert page is not None
    assert len(browser.tabs) == 2


async def test_reap_leaves_capacity_intact_for_later_searches(monkeypatch):
    """Reaping frees memory; it must not narrow how many scrapes can run."""
    browser = FakeBrowser()
    pool = main.TabPool(browser, 3)
    monkeypatch.setattr(main, "TAB_IDLE_TTL", -1.0)

    async def worker():
        async with pool.lease():
            await asyncio.sleep(0.01)

    await asyncio.gather(*[worker() for _ in range(3)])
    for _ in range(5):
        await asyncio.sleep(0)
    await pool.reap()

    live = 0
    peak = 0

    async def counted():
        nonlocal live, peak
        async with pool.lease():
            live += 1
            peak = max(peak, live)
            await asyncio.sleep(0.01)
            live -= 1

    await asyncio.gather(*[counted() for _ in range(3)])
    assert peak == 3


async def test_lease_prefers_a_warm_tab_over_opening_a_new_one():
    """The whole point of the pool: never pay tab setup twice for one slot."""
    browser = FakeBrowser()
    pool = main.TabPool(browser, 4)
    for _ in range(5):
        async with pool.lease():
            pass
        for _ in range(5):
            await asyncio.sleep(0)
    assert len(browser.tabs) == 1, "serial searches must keep reusing one tab"


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

def test_cache_round_trip_and_expiry(clean_state, monkeypatch):
    main._cache_put("milk", {"blinkit": "x"})
    assert main._cache_get("milk") == {"blinkit": "x"}

    monkeypatch.setattr(main, "SEARCH_CACHE_TTL", -1.0)
    main._cache_put("bread", {"zepto": "y"})
    assert main._cache_get("bread") is None
    assert "bread" not in main._pool_cache, "an expired entry should not linger"


def test_cache_evicts_at_the_ceiling(clean_state, monkeypatch):
    monkeypatch.setattr(main, "SEARCH_CACHE_MAX", 3)
    for i in range(5):
        main._cache_put(f"q{i}", {"n": i})
    assert len(main._pool_cache) <= 3


# ---------------------------------------------------------------------------
# Single-flight
# ---------------------------------------------------------------------------

async def test_duplicate_concurrent_queries_scrape_once(stub_platforms):
    browser = FakeBrowser()
    main.app.state.pool = main.TabPool(browser, 4)
    for stub in stub_platforms.values():
        stub.delay = 0.05

    a, b = await asyncio.gather(main._gather_pools("milk"), main._gather_pools(" MILK "))
    for key, stub in stub_platforms.items():
        assert stub.calls == 1, f"{key} was scraped twice for one question"
    assert a["blinkit"].products == b["blinkit"].products


async def test_second_query_is_served_from_cache(stub_platforms):
    browser = FakeBrowser()
    main.app.state.pool = main.TabPool(browser, 4)
    await main._gather_pools("milk")
    await main._gather_pools("milk")
    for stub in stub_platforms.values():
        assert stub.calls == 1


async def test_a_round_of_failures_is_not_cached(stub_platforms):
    browser = FakeBrowser()
    main.app.state.pool = main.TabPool(browser, 4)
    for stub in stub_platforms.values():
        stub.result = common.ScrapeResult([], common.BLOCKED, "nope")

    await main._gather_pools("milk")
    assert main._cache_get("milk") is None, "caching a block would serve it for the whole TTL"


async def test_a_hung_up_client_does_not_cancel_the_shared_scrape(stub_platforms):
    browser = FakeBrowser()
    main.app.state.pool = main.TabPool(browser, 4)
    for stub in stub_platforms.values():
        stub.delay = 0.1

    leaver = asyncio.create_task(main._gather_pools("milk"))
    await asyncio.sleep(0.01)
    stayer = asyncio.create_task(main._gather_pools("milk"))
    await asyncio.sleep(0.01)
    leaver.cancel()

    pools = await stayer
    assert pools["blinkit"].status == common.OK
    for stub in stub_platforms.values():
        assert stub.calls == 1


async def test_inflight_entry_is_cleared_when_the_scrape_finishes(stub_platforms):
    browser = FakeBrowser()
    main.app.state.pool = main.TabPool(browser, 4)
    await main._gather_pools("milk")
    await asyncio.sleep(0)
    assert main._inflight == {}, "a leaked in-flight entry would pin a stale scrape forever"


async def test_a_scraper_exception_becomes_an_error_column(stub_platforms):
    browser = FakeBrowser()
    main.app.state.pool = main.TabPool(browser, 4)
    stub_platforms["zepto"].raises = ValueError("boom")

    pools = await main._gather_pools("milk")
    assert pools["zepto"].status == common.ERROR
    assert "boom" in pools["zepto"].message
    assert pools["blinkit"].status == common.OK, "one bad platform must not sink the rest"


# ---------------------------------------------------------------------------
# View shaping
# ---------------------------------------------------------------------------

def test_shape_sends_the_visible_page_and_the_pool_behind_it():
    pool = common.ScrapeResult(
        [product(f"milk {i}", "10", "20") for i in range(20)], common.OK
    )
    shaped = main._shape(pool, common.SORT_RELEVANCE, 0)
    assert len(shaped["products"]) == common.MAX_PRODUCTS
    assert len(shaped["pool"]) == 20, "the browser re-sorts from the pool, not the page"
    assert shaped["matched"] == 20
    assert shaped["products"] == shaped["pool"][:common.MAX_PRODUCTS]


def test_shape_reports_a_filter_wipeout_as_empty_not_as_the_platform_failing():
    pool = common.ScrapeResult([product("milk", "10")], common.OK)
    shaped = main._shape(pool, common.SORT_RELEVANCE, 50)
    assert shaped["products"] == []
    assert shaped["status"] == common.EMPTY
    assert "50%" in shaped["message"]
    assert shaped["pool"], "the pool stays whole so the browser can undo the filter"


def test_shape_preserves_a_platform_level_failure():
    shaped = main._shape(common.ScrapeResult([], common.BLOCKED, "challenged"), "relevance", 0)
    assert shaped["status"] == common.BLOCKED
    assert shaped["message"] == "challenged"
    assert shaped["matched"] == 0


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

async def test_search_endpoint_returns_every_platform(stub_platforms):
    browser = FakeBrowser()
    main.app.state.pool = main.TabPool(browser, 4)
    out = await main.search(q="milk", sort="relevance", min_discount=0)
    assert set(out) == set(main.KEYS)
    for key in main.KEYS:
        assert out[key]["status"] == common.OK
        assert out[key]["products"]
        assert "pool" in out[key]


async def _drain(response):
    chunks = []
    async for chunk in response.body_iterator:
        chunks.append(chunk if isinstance(chunk, str) else chunk.decode())
    return "".join(chunks)


def _parse_sse(text):
    events = []
    for block in text.strip().split("\n\n"):
        if not block.strip():
            continue
        name, data = None, None
        for line in block.splitlines():
            if line.startswith("event: "):
                name = line[len("event: "):]
            elif line.startswith("data: "):
                data = json.loads(line[len("data: "):])
        events.append((name, data))
    return events


async def test_stream_emits_a_column_per_platform_then_done(stub_platforms):
    browser = FakeBrowser()
    main.app.state.pool = main.TabPool(browser, 4)

    events = _parse_sse(await _drain(await main.search_stream(q="milk", sort="relevance", min_discount=0)))
    results = [d for n, d in events if n == "result"]
    assert {d["service"] for d in results} == set(main.KEYS)
    assert events[-1][0] == "done"
    assert events[-1][1]["served"] == len(main.KEYS)
    for d in results:
        assert d["products"], "a streamed column carries the same payload as the batch API"
        assert "pool" in d


async def test_stream_yields_the_fastest_platform_first(stub_platforms):
    browser = FakeBrowser()
    main.app.state.pool = main.TabPool(browser, len(main.KEYS))
    for i, key in enumerate(main.KEYS):
        # Reverse order, so arrival order cannot accidentally match KEYS order.
        stub_platforms[key].delay = 0.02 * (len(main.KEYS) - i)

    events = _parse_sse(await _drain(await main.search_stream(q="milk", sort="relevance", min_discount=0)))
    order = [d["service"] for n, d in events if n == "result"]
    assert order == list(reversed(main.KEYS)), (
        "streaming exists so the first column does not wait on the slowest"
    )


async def test_stream_serves_a_cached_pool_without_rescraping(stub_platforms):
    browser = FakeBrowser()
    main.app.state.pool = main.TabPool(browser, 4)
    await main._gather_pools("milk")

    events = _parse_sse(await _drain(await main.search_stream(q="milk", sort="relevance", min_discount=0)))
    assert len([1 for n, _ in events if n == "result"]) == len(main.KEYS)
    for stub in stub_platforms.values():
        assert stub.calls == 1


async def test_stream_and_batch_clients_share_one_scrape(stub_platforms):
    browser = FakeBrowser()
    main.app.state.pool = main.TabPool(browser, 4)
    for stub in stub_platforms.values():
        stub.delay = 0.05

    stream = asyncio.create_task(_drain(await main.search_stream(q="milk", sort="relevance", min_discount=0)))
    batch = asyncio.create_task(main.search(q="milk", sort="relevance", min_discount=0))
    text, out = await asyncio.gather(stream, batch)

    assert len([1 for n, _ in _parse_sse(text) if n == "result"]) == len(main.KEYS)
    assert set(out) == set(main.KEYS)
    for stub in stub_platforms.values():
        assert stub.calls == 1


async def test_set_location_clears_the_cache(stub_platforms):
    browser = FakeBrowser()
    main.app.state.pool = main.TabPool(browser, 4)
    await main._gather_pools("milk")
    assert main._cache_get("milk") is not None

    out = await main.set_location(main.LocationRequest(location="201306"))
    assert out == {k: True for k in main.KEYS}
    assert main._cache_get("milk") is None, "a new pincode makes cached prices wrong"


async def test_a_platform_that_refuses_a_location_does_not_fail_the_rest(stub_platforms):
    browser = FakeBrowser()
    main.app.state.pool = main.TabPool(browser, 4)
    stub_platforms["jiomart"].loc_ok = False

    out = await main.set_location(main.LocationRequest(location="201306"))
    assert out["jiomart"] is False
    assert out["blinkit"] is True


async def test_a_scrape_that_straddles_a_location_change_is_neither_cached_nor_joined(stub_platforms):
    """Its prices are for the old pincode, so it must not outlive the change."""
    browser = FakeBrowser()
    # Room for both scrapes at once, so set_location never queues for a tab.
    main.app.state.pool = main.TabPool(browser, 2 * len(main.KEYS))
    for stub in stub_platforms.values():
        stub.delay = 0.2

    old = asyncio.create_task(main._gather_pools("milk"))
    await asyncio.sleep(0.05)
    await main.set_location(main.LocationRequest(location="400001"))
    new = asyncio.create_task(main._gather_pools("milk"))

    await old
    assert main._cache_get("milk") is None, "old-location prices were cached after the change"

    # The old scrape has finished; its cleanup must not have evicted the scrape
    # that replaced it, or this client would start a third round of traffic.
    joiner = asyncio.create_task(main._gather_pools("milk"))
    await asyncio.gather(new, joiner)
    for key, stub in stub_platforms.items():
        # `pages` counts searches only; set_location also bumps `calls`.
        assert len(stub.pages) == 2, f"{key}: expected the old scrape and one new one"
    assert main._cache_get("milk") is not None, "the new-location scrape should cache"


async def test_stream_chunks_leave_the_app_as_they_land(stub_platforms):
    """The point of the endpoint is incrementality, so assert it at the wire.

    Driven through the ASGI callable rather than a client, because an HTTP
    client that buffers the body would make a fully batched response look
    perfectly streamed. A middleware that buffers would regress this silently.
    """
    browser = FakeBrowser()
    main.app.state.pool = main.TabPool(browser, len(main.KEYS))
    for i, key in enumerate(main.KEYS):
        stub_platforms[key].delay = 0.05 * (i + 1)

    loop = asyncio.get_running_loop()
    started = loop.time()
    stamps = []
    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
        "method": "GET", "scheme": "http", "path": "/api/search/stream",
        "raw_path": b"/api/search/stream", "query_string": b"q=milk",
        "root_path": "", "headers": [(b"host", b"t"), (b"accept-encoding", b"gzip")],
        "client": ("1.2.3.4", 1), "server": ("t", 80),
    }

    sent_request = False

    async def receive():
        # Must genuinely yield: a coroutine returning without awaiting starves
        # the loop, and Starlette polls receive() for a client disconnect.
        nonlocal sent_request
        if not sent_request:
            sent_request = True
            return {"type": "http.request", "body": b"", "more_body": False}
        await asyncio.sleep(30)

    async def send(message):
        if message["type"] == "http.response.body" and message.get("body"):
            text = message["body"].decode()
            if '"service"' in text:
                stamps.append(loop.time() - started)

    await asyncio.wait_for(main.app(scope, receive, send), timeout=10)

    assert len(stamps) == len(main.KEYS)
    assert stamps[0] < stamps[-1] / 2, (
        f"columns left the app all at once ({stamps}) -- something is buffering"
    )


async def test_services_carries_the_page_size_the_browser_slices_with():
    """The browser cuts the visible page out of the pool, so it needs this."""
    response = await main.services()
    body = json.loads(bytes(response.body))
    assert body["maxProducts"] == common.MAX_PRODUCTS
    assert [s["key"] for s in body["services"]] == main.KEYS
    assert "max-age" in response.headers["cache-control"]


# ---------------------------------------------------------------------------
# Scheduling
# ---------------------------------------------------------------------------

def test_unmeasured_platforms_are_scheduled_first(clean_state):
    main._DURATIONS.update({k: 1.0 for k in main.KEYS[:-1]})
    # The last platform has never been timed, so it must not stay at the back.
    assert main._scrape_order()[0] == main.KEYS[-1]


def test_platforms_are_scheduled_slowest_first(clean_state):
    for i, key in enumerate(main.KEYS):
        main._DURATIONS[key] = float(i)
    assert main._scrape_order() == list(reversed(main.KEYS))


def test_duration_is_an_average_not_the_last_reading(clean_state):
    main._record_duration("blinkit", 10.0)
    main._record_duration("blinkit", 0.0)
    # One freak fast run must not convince us the platform is fast.
    assert 0.0 < main._DURATIONS["blinkit"] < 10.0


async def test_the_slowest_platform_is_started_first_next_time(stub_platforms):
    """The tail of a search is whichever platforms had to queue for a tab."""
    browser = FakeBrowser()
    # Deliberately smaller than the platform count, so order decides the tail.
    main.app.state.pool = main.TabPool(browser, 2)
    slowest = main.KEYS[-1]
    for key in main.KEYS:
        stub_platforms[key].delay = 0.15 if key == slowest else 0.02

    await main._gather_pools("milk")
    assert main._scrape_order()[0] == slowest, (
        "registry order starts the slowest platform last; it should not stay there"
    )

    main._pool_cache.clear()
    order = []
    original = main.search_svc

    async def recording(pool, key, term):
        order.append(key)
        return await original(pool, key, term)

    main.search_svc = recording
    try:
        await main._gather_pools("bread")
    finally:
        main.search_svc = original
    assert order[0] == slowest


async def test_queueing_time_is_not_counted_against_a_platform(stub_platforms):
    """A platform must not look slow for having been scheduled late."""
    browser = FakeBrowser()
    main.app.state.pool = main.TabPool(browser, 1)  # everything queues
    for stub in stub_platforms.values():
        stub.delay = 0.05

    await main._gather_pools("milk")
    for key, seen in main._DURATIONS.items():
        assert seen < 0.15, (
            f"{key} recorded {seen:.2f}s for a 0.05s scrape -- queueing leaked in"
        )


async def test_prewarm_opens_the_pool_so_the_first_search_does_not():
    browser = FakeBrowser()
    pool = main.TabPool(browser, 3)
    await pool.prewarm()
    for _ in range(8):
        await asyncio.sleep(0)

    assert len(browser.tabs) == 3
    async with pool.lease() as page:
        assert page in browser.tabs, "a prewarmed tab should be handed straight out"
    assert len(browser.tabs) == 3, "prewarming then leasing must not open a fourth"
