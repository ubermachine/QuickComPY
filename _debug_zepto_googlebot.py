import asyncio
import zendriver as zd
from backend_py.scrapers.zepto import inject_location_cookies, resolve_coords

async def main():
    # Googlebot user agent
    ua = 'Mozilla/5.0 (Linux; Android 6.0.1; Nexus 5X Build/MMB29P) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/W.X.Y.Z Mobile Safari/537.36 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)'
    config = zd.Config(headless=True, disable_webrtc=True, user_agent=ua)
    browser = await zd.start(config=config)
    try:
        page = await browser.get('about:blank', new_tab=True)
        # Apply stealth
        await page.send(zd.cdp.page.add_script_to_evaluate_on_new_document(source="""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        """))
        
        await page.get("https://www.zepto.com/")
        await asyncio.sleep(2)
        
        coords = resolve_coords('201301')
        await inject_location_cookies(page, '201301', str(coords['lat']), str(coords['lon']))
        
        await page.get("https://www.zepto.com/search?query=milk")
        await asyncio.sleep(6)
        
        h = await page.get_content()
        with open("zepto_googlebot.html", "w", encoding="utf-8") as f:
            f.write(h)
            
        if "Oops! Please login" in h:
            print("Googlebot is also blocked by login wall!")
        else:
            print("Googlebot bypassed the login wall!")
            
    finally:
        await browser.stop()

if __name__ == "__main__":
    asyncio.run(main())
