import asyncio
import time
import threading
import zendriver as zd
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
    print("Setting location...")
    await set_location(page1, "201301")
    await page1.close()

    page2 = await stealth_new_page(browser)
    print("Searching...")
    products = await search(page2, "eggs")
    print(f"Found {len(products)} products.")
    await page2.close()

if __name__ == "__main__":
    browser, loop = get_browser_and_loop()
    run_async_task(do_test(browser), loop)
