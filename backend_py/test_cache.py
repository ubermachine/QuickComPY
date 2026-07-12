import asyncio
import threading
import zendriver as zd
import time

def start_background_loop(loop):
    print("Background loop starting...")
    asyncio.set_event_loop(loop)
    loop.run_forever()

def get_browser_and_loop():
    print("Starting global Zendriver browser...")
    loop = asyncio.new_event_loop()
    t = threading.Thread(target=start_background_loop, args=(loop,), daemon=True)
    t.start()
    
    # Wait a bit for loop to start
    time.sleep(1)
    
    # Start browser in the background loop
    print("Submitting zd.start...")
    future = asyncio.run_coroutine_threadsafe(zd.start(config=zd.Config(sandbox=False, headless=True)), loop)
    print("Waiting for result...")
    browser = future.result()
    print("Browser started:", browser)
    return browser, loop

if __name__ == "__main__":
    get_browser_and_loop()
    print("Success")
