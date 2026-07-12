import sys, asyncio, json
sys.stdout.reconfigure(encoding='utf-8')

import zendriver as zd
from curl_cffi import requests
from backend_py.awswaf.aws import AwsWaf

async def main():
    # Solve WAF
    session = requests.Session(impersonate="chrome")
    session.headers.update({
        'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'accept-language': 'en-US,en;q=0.9',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/136.0.0.0 Safari/537.36',
    })
    resp = session.get('https://www.swiggy.com/instamart', timeout=30)
    goku, host = AwsWaf.extract(resp.text)
    token = AwsWaf(goku, host, 'www.swiggy.com')()
    print(f'Token: {token[:60]}...')

    # Launch Zendriver with token cookie pre-set
    browser = await zd.start(config=zd.Config(sandbox=False, headless=True))
    page = await browser.get('about:blank', new_tab=True)
    
    # Inject cookie via CDP BEFORE navigating
    await page.send(zd.cdp.network.set_cookie(
        name='aws-waf-token', value=token,
        domain='.swiggy.com', path='/'
    ))
    
    # Navigate and check
    await page.get('https://www.swiggy.com/instamart/search?query=eggs')
    await asyncio.sleep(6)
    
    content = await page.get_content()
    waf = 'Something went wrong' in content or 'Try Again' in content
    print(f'Content: {len(content)} chars, WAF: {waf}')

    if not waf:
        print('*** WAF BYPASSED! ***')
        if len(content) > 50000:
            prods = await page.evaluate("""() => {
                const r = []; document.querySelectorAll('a, div').forEach(el => {
                    const t = (el.textContent||'').trim();
                    if (t.includes('₹') && t.length < 300) r.push(t.substring(0,200));
                }); return [...new Set(r)].slice(0,10);
            }""")
            print(f'Products found: {json.dumps(prods, ensure_ascii=False)}')
    else:
        print('Token not accepted. Falling back.')

    await browser.stop()

asyncio.run(main())
