import sys
if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

import asyncio
import zendriver as zd
from backend_py.scrapers.instamart import set_location, search

async def main():
    browser = await zd.start(config=zd.Config(sandbox=False, headless=True))
    try:
        page = await browser.get('about:blank', new_tab=True)
        await set_location(page, "110001")
        
        page2 = await browser.get('about:blank', new_tab=True)
        products = await search(page2, "eggs")
        print(f"Found {len(products)} products on Instamart")
        if products:
            print(products[0])
            
        html = await page2.get_content()
        with open("im_debug.html", "w", encoding="utf-8") as f:
            f.write(html)
        
        inner_text = await page2.evaluate("() => document.body.innerText")
        with open("im_debug_text.txt", "w", encoding="utf-8") as f:
            f.write(str(inner_text))
            
        await page2.save_screenshot("im_debug.png")
        print("Saved debug screenshot, HTML, and innerText")
    finally:
        await browser.stop()

if __name__ == "__main__":
    asyncio.run(main())
