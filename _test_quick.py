import sys, asyncio, json
sys.stdout.reconfigure(encoding='utf-8')

import zendriver as zd
from curl_cffi import requests
from backend_py.awswaf.aws import AwsWaf

async def solve_and_browse():
    # Step 1: Solve WAF via awswaf (curl_cffi)
    print('[1] Getting WAF challenge...')
    session = requests.Session(impersonate="chrome")
    session.headers.update({
        'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'accept-language': 'en-US,en;q=0.9',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/136.0.0.0 Safari/537.36',
    })
    resp = session.get('https://www.swiggy.com/instamart', timeout=30)
    goku, host = AwsWaf.extract(resp.text)
    
    print(f'[2] Solving...')
    token = AwsWaf(goku, host, 'www.swiggy.com')()
    print(f'[3] Token: {token[:60]}...')

    # Step 2: Open browser, inject token, navigate
    print('[4] Opening Zendriver browser...')
    browser = await zd.start(config=zd.Config(sandbox=False, headless=True))
    page = await browser.get('about:blank', new_tab=True)
    
    # Inject WAF token via CDP cookie
    await page.send(zd.cdp.network.set_cookie(
        name='aws-waf-token',
        value=token,
        domain='.swiggy.com',
        path='/'
    ))
    print('[5] Token cookie injected')
    
    # Navigate to search page
    await page.get('https://www.swiggy.com/instamart/search?query=eggs')
    await asyncio.sleep(5)
    
    url = page.url
    content = await page.content()
    print(f'[6] URL: {url}')
    print(f'[7] Content: {len(content)} chars')
    
    waf = 'Something went wrong' in content or 'Try Again' in content
    print(f'[8] WAF blocked: {waf}')
    
    if not waf and len(content) > 30000:
        print('[9] SUCCESS! Page loaded with products!')
        with open('im_waf_solved.html', 'w', encoding='utf-8') as f:
            f.write(content[:200000])
        # Try to extract products
        prods = await page.evaluate("""() => {
            const items = document.querySelectorAll('[class*="product"],[class*="Product"],[data-testid],a[href*="/product/"]');
            return [...items].slice(0,10).map(el => ({
                tag: el.tagName,
                text: (el.textContent||'').trim().substring(0,200),
                cls: (el.className||'').substring(0,50)
            })).filter(x => x.text.length > 5 && x.text.includes('₹'));
        }""")
        print(f'Products: {json.dumps(prods, indent=2, ensure_ascii=False)[:2000]}')
    
    await browser.stop()

asyncio.run(solve_and_browse())
