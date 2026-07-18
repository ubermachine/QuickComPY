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
        
        # Navigate and set cookies
        await page.get("https://www.zepto.com/")
        await asyncio.sleep(2)
        
        coords = resolve_coords('201301')
        await inject_location_cookies(page, '201301', str(coords['lat']), str(coords['lon']))
        
        # Reload homepage
        await page.get("https://www.zepto.com/")
        await asyncio.sleep(3)
        
        # See if there's a search input on the home page
        print("Looking for search input on homepage...")
        try:
            # We saw this in the previous HTML: <input ... placeholder="Search for over 5000 products" ...>
            input_sel = 'input[placeholder*="Search"]'
            await page.wait_for(input_sel, timeout=5)
            await page.click(input_sel)
            await asyncio.sleep(1)
            # Type into it
            print("Typing 'milk' into search bar...")
            # We can use cdp to type or page.type
            # zendriver page.type? zd does not have page.type, we must evaluate or send key events
            await page.evaluate("""
                let inp = document.querySelector('input[placeholder*="Search"]');
                if(inp) {
                    inp.value = 'milk';
                    inp.dispatchEvent(new Event('input', { bubbles: true }));
                    inp.dispatchEvent(new Event('change', { bubbles: true }));
                    // Press Enter
                    inp.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true}));
                }
            """)
            await asyncio.sleep(5)
            
            h = await page.get_content()
            with open("zepto_debug_ui.html", "w", encoding="utf-8") as f:
                f.write(h)
            
            print("Done typing. Check zepto_debug_ui.html to see if login wall appeared or products appeared.")
            
            # Check for "Oops! Please login"
            if "Oops! Please login" in h:
                print("STILL ASKING FOR LOGIN!")
            else:
                print("NO LOGIN WALL! Maybe products are there.")
                
        except Exception as e:
            print(f"Failed to find/type in search bar: {e}")
            h = await page.get_content()
            with open("zepto_debug_ui.html", "w", encoding="utf-8") as f:
                f.write(h)

    finally:
        await browser.stop()

if __name__ == "__main__":
    asyncio.run(main())
