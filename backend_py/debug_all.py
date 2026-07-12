import asyncio
import zendriver as zd

async def main():
    print("Starting zendriver...")
    browser = await zd.start(config=zd.Config(sandbox=False, headless=True))
    print("Browser started.")

    try:
        page = await browser.get('about:blank', new_tab=True)
        print("1. Navigating to Instamart Home...")
        await page.get("https://www.swiggy.com/instamart")
        await asyncio.sleep(3)
        
        # Inject location
        from backend_py.scrapers import instamart
        print("2. Injecting location...")
        await instamart.set_location(page, "bangalore")
        await asyncio.sleep(2)
        
        # Navigate to Search
        print("3. Navigating to Instamart Search...")
        await page.get("https://www.swiggy.com/instamart/search?query=milk")
        await asyncio.sleep(5)
        
        # Save HTML and screenshot
        html = await page.get_content()
        with open("instamart_all.html", "w", encoding="utf-8") as f:
            f.write(html)
        await page.save_screenshot("instamart_all.png")
        print("Saved html and screenshot.")
        
        await page.close()
    except Exception as e:
        print("Error:", e)
    finally:
        await browser.stop()

if __name__ == "__main__":
    asyncio.run(main())
