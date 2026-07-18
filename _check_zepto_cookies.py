import sys, asyncio, zendriver as zd
sys.stdout.reconfigure(encoding='utf-8')

_STEALTH = """Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
Object.defineProperty(navigator, 'plugins', { get: () => [1,2,3,4,5] });
Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
window.chrome = { runtime: {} };"""

async def test_location(browser, pincode, lat, lon):
    print(f"\n==========================================")
    print(f"Testing location pincode: {pincode} (lat={lat}, lon={lon})")
    
    page = await browser.get("about:blank", new_tab=True)
    await page.send(zd.cdp.page.add_script_to_evaluate_on_new_document(source=_STEALTH))
    
    try:
        # 1. Establish session
        await page.get("https://www.zepto.com/")
        await asyncio.sleep(2)
        
        # 2. Inject cookies
        domain = ".zepto.com"
        user_pos = f'{{"latitude":{lat},"longitude":{lon}}}'
        await page.send(zd.cdp.network.set_cookie(name='latitude', value=lat, domain=domain, path='/', secure=True))
        await page.send(zd.cdp.network.set_cookie(name='longitude', value=lon, domain=domain, path='/', secure=True))
        await page.send(zd.cdp.network.set_cookie(name='user_position', value=user_pos, domain=domain, path='/', secure=True))
        await page.send(zd.cdp.network.set_cookie(name='location', value=pincode, domain=domain, path='/', secure=True))
        
        # 3. Navigate to search page
        await page.get("https://www.zepto.com/search?query=milk")
        await asyncio.sleep(5)
        
        # 4. Check text content
        html = await page.get_content()
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        body_text = " ".join(soup.get_text().split())
        print(f"Body text snippet: {body_text[:300]}")
        
        # Check if products exist
        products = []
        for card in soup.find_all("a", href=lambda h: h and "/pn/" in h):
            text = card.get_text().strip()
            if "₹" in text:
                products.append(text)
                
        print(f"Products found count: {len(products)}")
        if products:
            print(f"  First product: {' '.join(products[0].split())[:120]}")
            
    except Exception as e:
        print("Error during test:", e)
    finally:
        await page.close()

async def main():
    config = zd.Config(
        sandbox=False,
        headless=True,
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36',
        disable_webrtc=True,
    )
    browser = await zd.start(config=config)
    try:
        # Test Noida
        await test_location(browser, "201301", "28.5821195", "77.3266991")
        # Test Delhi Connaught Place
        await test_location(browser, "110001", "28.6327426", "77.2195969")
        # Test Mumbai
        await test_location(browser, "400001", "18.9400", "72.8353")
        # Test Bangalore
        await test_location(browser, "560001", "12.9716", "77.5946")
    finally:
        await browser.stop()

if __name__ == "__main__":
    asyncio.run(main())
