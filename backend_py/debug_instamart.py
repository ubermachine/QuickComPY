import asyncio
import zendriver as zd
from backend_py.scrapers import instamart

async def main():
    print("Starting zendriver...")
    browser = await zd.start(config=zd.Config(sandbox=False, headless=True))
    print("Browser started.")

    try:
        page = await browser.get('about:blank', new_tab=True)
        print("Setting location for Instamart...")
        await instamart.set_location(page, "bangalore")
        await asyncio.sleep(2)
        print("URL after set_location:", page.url)
        
        # Navigate to search URL
        import urllib.parse
        encoded = urllib.parse.quote("milk")
        search_url = f"https://www.swiggy.com/instamart/search?query={encoded}"
        print("Navigating to search URL:", search_url)
        await page.get(search_url)
        await asyncio.sleep(5)
        print("URL after navigation:", page.url)
        
        html = await page.get_content()
        print("Body length:", len(html))
        print("Title:", await page.evaluate("document.title"))
        
        # Check if there are products
        products = await instamart.extract_from_html(page)
        print(f"Products found: {len(products)}")
        
        await page.save_screenshot("instamart_debug.png")
        with open("instamart_debug.html", "w", encoding="utf-8") as f:
            f.write(html)
            
        await page.close()
    except Exception as e:
        print("Error:", e)
    finally:
        await browser.stop()

if __name__ == "__main__":
    asyncio.run(main())
