import asyncio
import zendriver as zd
from backend_py.scrapers.zepto import inject_location_cookies, resolve_coords

async def main():
    config = zd.Config(headless=True, disable_webrtc=True, user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36')
    browser = await zd.start(config=config)
    try:
        page = await browser.get('about:blank', new_tab=True)
        # Apply stealth
        await page.send(zd.cdp.page.add_script_to_evaluate_on_new_document(source="""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        """))
        
        await page.get("https://www.zepto.com/")
        await asyncio.sleep(3)
        
        coords = resolve_coords('201301')
        await inject_location_cookies(page, '201301', str(coords['lat']), str(coords['lon']))
        
        await page.get("https://www.zepto.com/search?query=milk")
        await asyncio.sleep(5)
        
        cookies = await page.send(zd.cdp.network.get_cookies())
        print("ALL COOKIES:")
        for c in cookies:
            print(f"{c.name}: {c.value[:50]}")
            
    finally:
        await browser.stop()

if __name__ == "__main__":
    asyncio.run(main())
