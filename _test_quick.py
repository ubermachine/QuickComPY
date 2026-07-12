import sys, asyncio, json
sys.stdout.reconfigure(encoding='utf-8')
import zendriver as zd

STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
Object.defineProperty(navigator, 'plugins', { get: () => [1,2,3,4,5] });
Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
window.chrome = { runtime: {} };
Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
"""

async def test():
    browser = await zd.start(config=zd.Config(sandbox=False, headless=True))
    page = await browser.get('about:blank', new_tab=True)
    
    # Inject stealth script that persists across navigations
    await page.send(zd.cdp.page.add_script_to_evaluate_on_new_document(source=STEALTH_JS))
    
    print('Testing Bigbasket with stealth injections...')
    await page.get('https://www.bigbasket.com/ps/?q=eggs')
    await asyncio.sleep(5)
    
    content = await page.get_content()
    title = await page.evaluate('document.title')
    print(f'Title: {title}')
    print(f'Content: {len(content)} chars')
    
    if 'Access Denied' in content:
        print('Still blocked by Akamai')
    elif len(content) > 50000:
        print('PAGE LOADED! Checking for products...')
        has_products = '₹' in content
        print(f'Has prices: {has_products}')
        if has_products:
            prods = await page.evaluate("""(() => {
                const cards = document.querySelectorAll('li, [class*="product"]');
                const results = [];
                cards.forEach(c => {
                    const t = c.textContent.replace(/\\s+/g,' ').trim();
                    if (t.includes('₹') && t.length > 50) results.push(t.substring(0,200));
                });
                return results.slice(0,5);
            })()""")
            print(f'Products: {json.dumps(prods, ensure_ascii=False)}')
    else:
        print(f'Page content: {content[:500]}')
    
    await browser.stop()

asyncio.run(test())
