import sys, asyncio, json, os
sys.stdout.reconfigure(encoding='utf-8')
os.environ['PYTHONIOENCODING'] = 'utf-8'

from camoufox.async_api import AsyncCamoufox

async def test_instamart():
    print("Starting Camoufox...")
    async with AsyncCamoufox(headless=True, humanize=True) as browser:
        ctx = await browser.new_context(no_viewport=True)
        page = await ctx.new_page()
        
        print("Loading Swiggy Instamart homepage...")
        await page.goto("https://www.swiggy.com/instamart", wait_until="networkidle", timeout=60000)
        await asyncio.sleep(3)  # Let React render
        
        content = await page.content()
        print(f"Homepage: {len(content)} chars, WAF: {'Something went wrong' in content}")
        
        # Debug the page structure
        page_info = await page.evaluate("""() => {
            const info = {};
            // Find inputs
            const inputs = document.querySelectorAll('input');
            info.inputs = [...inputs].map(i => ({
                type: i.type, placeholder: i.placeholder, 
                role: i.getAttribute('role'),
                id: i.id,
                className: (i.className||'').substring(0,50)
            }));
            // Find links/buttons with "search"
            const searchEls = document.querySelectorAll('a[href*="search"], button, [class*="Search"], [class*="search"]');
            info.searchEls = [...searchEls].slice(0,10).map(e => ({
                tag: e.tagName, text: (e.textContent||'').trim().substring(0,50),
                href: e.getAttribute('href') || '',
                cls: (e.className||'').substring(0,50)
            }));
            // Find navigation items
            const navs = document.querySelectorAll('nav a, [class*="nav"] a, header a');
            info.navLinks = [...navs].slice(0,10).map(a => ({
                text: (a.textContent||'').trim().substring(0,50),
                href: a.getAttribute('href')||''
            }));
            info.title = document.title;
            return info;
        }""")
        print(f"\nPage analysis: {json.dumps(page_info, indent=2, ensure_ascii=False)[:2000]}")
        
        # Try to use SPA navigation: set window.location to the search URL
        # This keeps the same page session (no reload via goto)
        print("\n[SAME-PAGE SEARCH] Using history API...")
        await page.evaluate("""() => {
            window.history.pushState({}, '', '/instamart/search?query=eggs');
            window.dispatchEvent(new PopStateEvent('popstate'));
        }""")
        await asyncio.sleep(5)
        
        # Check if this triggered the SPA to load search results
        url = page.url
        content2 = await page.content()
        print(f"  URL: {url}")
        print(f"  Content: {len(content2)} chars")
        
        if 'Something went wrong' in content2 or 'Try Again' in content2:
            print("  *** SPA navigation WAF blocked ***")
        else:
            print("  SPA navigation worked! Checking products...")
            prods = await page.evaluate("""() => {
                const items = document.querySelectorAll('[class*="product"], [class*="Product"], [data-testid], a[href*="/product/"]');
                return [...items].slice(0,10).map(el => ({
                    tag: el.tagName,
                    text: (el.textContent||'').trim().substring(0,200),
                    cls: (el.className||'').substring(0,50)
                })).filter(x => x.text.length > 5 && x.text.includes('₹'));
            }""")
            print(json.dumps(prods, indent=2, ensure_ascii=False)[:3000])
        
        with open('im_camoufox_search.html', 'w', encoding='utf-8') as f:
            f.write(content2[:200000])

asyncio.run(test_instamart())
