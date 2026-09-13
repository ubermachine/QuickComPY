"""Live check that a scraper works when driven from a background event loop.

This one needs a real Chromium *and* real network access to zepto.com, so it is
the only test here that can be prevented from running by the environment rather
than by the code. Where that happens it skips: an environment without a browser
is not a defect in the scraper.

Everything the test waits on is bounded. An unbounded wait here does not fail
one test, it hangs the entire pytest run -- which is exactly what used to
happen, because a failed browser start left the background loop dead and
``future.result()`` then waited forever for a loop that would never run again.
"""

import asyncio
import os
import sys
import threading

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import pytest
import zendriver as zd

from backend_py.scrapers import common
from backend_py.scrapers.zepto import set_location, search

# A browser that is going to start does so in seconds; past this we are waiting
# on something that is never going to arrive.
BROWSER_START_TIMEOUT = float(os.environ.get("ZEPTO_TEST_BROWSER_TIMEOUT", "30"))

# The scrape itself: set_location plus a search, both with their own internal
# budgets. This is the backstop for a browser that is up but wedged.
LIVE_SCRAPE_TIMEOUT = float(os.environ.get("ZEPTO_TEST_SCRAPE_TIMEOUT", "180"))

_STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
Object.defineProperty(navigator, 'plugins', { get: () => [1,2,3,4,5] });
Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
window.chrome = { runtime: {} };
Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
"""

ZEPTO_ORIGIN = "https://www.zepto.com/"


async def stealth_new_page(browser):
    page = await browser.get('about:blank', new_tab=True)
    await page.send(zd.cdp.page.add_script_to_evaluate_on_new_document(source=_STEALTH_JS))
    return page

def get_browser_and_loop():
    """Start a browser on its own loop in a background thread.

    Returns (browser, error, loop). `browser` is None when the browser could
    not be started, and `error` says why -- the caller skips on that rather
    than driving a loop that is no longer running.
    """
    loop = asyncio.new_event_loop()
    ready = threading.Event()
    state = {"browser": None, "error": None}

    def run_loop_and_browser():
        asyncio.set_event_loop(loop)
        try:
            stealth_config = zd.Config(
                sandbox=False,
                headless=True,
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36',
                disable_webrtc=True,
            )
            # Bounded: zd.start() reports a missing binary promptly, but a
            # browser that launches and never speaks CDP would otherwise leave
            # this thread -- and the test waiting on it -- stuck indefinitely.
            state["browser"] = loop.run_until_complete(
                asyncio.wait_for(zd.start(config=stealth_config),
                                 timeout=BROWSER_START_TIMEOUT)
            )
        except BaseException as e:
            state["error"] = e
            print(f"Failed to start Zendriver on background thread: {e}")
            ready.set()
            return
        ready.set()
        loop.run_forever()

    t = threading.Thread(target=run_loop_and_browser, daemon=True)
    t.start()

    # The thread bounds its own work; this is the backstop for it wedging
    # somewhere we did not bound, so that a broken environment cannot turn into
    # a pytest run that never terminates.
    if not ready.wait(BROWSER_START_TIMEOUT + 10):
        state["error"] = TimeoutError("browser thread never reported back")

    return state["browser"], state["error"], loop

def run_async_task(coro, loop, timeout=LIVE_SCRAPE_TIMEOUT):
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    try:
        return future.result(timeout)
    except BaseException:
        future.cancel()
        raise

def stop_loop(loop):
    try:
        loop.call_soon_threadsafe(loop.stop)
    except RuntimeError:
        # Already closed, or never ran: nothing left to stop.
        pass

async def origin_is_reachable(page):
    """Did the tab actually load zepto.com, or is there no route to it?

    Chrome parks a navigation it could not make on chrome-error://chromewebdata,
    which is the one outcome this test must skip on: no network is not a defect
    in the scraper. Anything that loads -- a challenge page included -- is the
    platform talking to us, and the assertions below stay in force for it.
    """
    try:
        await page.get(ZEPTO_ORIGIN)
        href = await page.evaluate("location.href")
    except Exception:
        return False
    return isinstance(href, str) and "zepto.com" in href


async def do_test(browser):
    probe = await stealth_new_page(browser)
    reachable = await origin_is_reachable(probe)
    await probe.close()
    if not reachable:
        pytest.skip("no network route to zepto.com from this environment")

    page1 = await stealth_new_page(browser)
    success = await set_location(page1, "201301")
    assert success is True, "Setting location failed"
    await page1.close()

    page2 = await stealth_new_page(browser)
    result = await search(page2, "eggs")
    await page2.close()

    # This test exists to prove zendriver works when driven from a background
    # thread, not to assert Zepto's stock levels. A block or an empty catalogue
    # is the platform's decision on the day, so skip those rather than report a
    # code defect; a broken interception still fails loudly below.
    if result.status in (common.BLOCKED, common.EMPTY):
        pytest.skip(f"Zepto returned {result.status} this run: {result.message}")
    assert result.status == common.OK, f"Unexpected status {result.status}: {result.message}"
    assert result.products, "No products found! The API interception might have failed."
    return result.products

def test_zepto_in_background_thread():
    browser, error, loop = get_browser_and_loop()
    if browser is None:
        stop_loop(loop)
        pytest.skip(f"no usable browser in this environment: {error!r}")
    try:
        products = run_async_task(do_test(browser), loop)
        print(f"Test passed! Found {len(products)} products.")
    finally:
        # The loop runs forever on a daemon thread; without this, pytest hangs
        # at exit waiting for it.
        try:
            run_async_task(browser.stop(), loop, timeout=30)
        except Exception:
            pass
        stop_loop(loop)

if __name__ == "__main__":
    test_zepto_in_background_thread()
