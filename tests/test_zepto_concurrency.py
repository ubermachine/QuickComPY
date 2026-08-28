import asyncio
import time
import threading
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import pytest
import zendriver as zd

from backend_py.scrapers import common
from backend_py.scrapers.zepto import set_location, search

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

def get_browser_and_loop():
    loop = asyncio.new_event_loop()
    
    def run_loop_and_browser():
        asyncio.set_event_loop(loop)
        try:
            stealth_config = zd.Config(
                sandbox=False,
                headless=True,
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36',
                disable_webrtc=True,
            )
            browser = loop.run_until_complete(zd.start(config=stealth_config))
            loop.zendriver_browser = browser
            
            async def init_sem():
                loop.global_semaphore = asyncio.Semaphore(2)
            loop.run_until_complete(init_sem())
            
            loop.run_forever()
        except Exception as e:
            print(f"Failed to start Zendriver on background thread: {e}")
            loop.zendriver_browser = None
            
    t = threading.Thread(target=run_loop_and_browser, daemon=True)
    t.start()
    
    while not hasattr(loop, 'zendriver_browser'):
        time.sleep(0.1)
        
    return loop.zendriver_browser, loop

def run_async_task(coro, loop):
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    try:
        return future.result()
    except BaseException:
        future.cancel()
        raise

async def do_test(browser):
    page1 = await stealth_new_page(browser)
    success = await set_location(page1, "201301")
    assert success is True, "Setting location failed"
    await page1.close()

    page2 = await stealth_new_page(browser)
    result = await search(page2, "eggs")
    await page2.close()

    # A block is the platform's decision, not a code defect -- fail loudly on a
    # broken interception, but skip rather than red-flag a bot challenge.
    if result.status == common.BLOCKED:
        pytest.skip(f"Zepto blocked this run: {result.message}")
    assert result.status == common.OK, f"Unexpected status {result.status}: {result.message}"
    assert result.products, "No products found! The API interception might have failed."
    return result.products

def test_zepto_in_background_thread():
    browser, loop = get_browser_and_loop()
    try:
        products = run_async_task(do_test(browser), loop)
        print(f"Test passed! Found {len(products)} products.")
    finally:
        # The loop runs forever on a daemon thread; without this, pytest hangs
        # at exit waiting for it.
        try:
            run_async_task(browser.stop(), loop)
        except Exception:
            pass
        loop.call_soon_threadsafe(loop.stop)

if __name__ == "__main__":
    test_zepto_in_background_thread()
