import sys, asyncio, json
sys.stdout.reconfigure(encoding='utf-8')

import zendriver as zd
from curl_cffi import requests
from backend_py.awswaf.aws import AwsWaf

async def main():
    # 1) Solve WAF token via curl_cffi with specific Chrome version
    session = requests.Session(impersonate="chrome136")  # specific version
    session.headers.update({
        'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'accept-language': 'en-US,en;q=0.9',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/136.0.0.0 Safari/537.36',
    })
    
    try:
        resp = session.get('https://www.swiggy.com/instamart', timeout=30)
        goku, host = AwsWaf.extract(resp.text)
        token = AwsWaf(goku, host, 'www.swiggy.com')()
        print(f'Token generated: {token[:60]}...')
    except Exception as e:
        print(f'Token generation failed: {e}')
        return

    # 2) Inject into Zendriver browser with stealth
    browser = await zd.start(config=zd.Config(sandbox=False, headless=True))
    
    # First navigate to set up domain cookies
    page = await browser.get('about:blank', new_tab=True)
    await page.send(zd.cdp.page.add_script_to_evaluate_on_new_document(
        source="""
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        window.chrome = { runtime: {} };
        """
    ))
    
    # Inject WAF token as cookie
    await page.send(zd.cdp.network.set_cookie(
        name='aws-waf-token', value=token,
        domain='.swiggy.com', path='/'
    ))
    print('Token cookie injected. Navigating...')

    # Navigate
    await page.get('https://www.swiggy.com/instamart/search?query=eggs')
    await asyncio.sleep(6)
    
    content = await page.get_content()
    waf = 'Something went wrong' in content or 'Try Again' in content
    print(f'Content: {len(content)} chars, WAF blocked: {waf}')
    
    if waf:
        print('Swiggy WAF still blocking.')
        print('Recommended: Use the Go awswaf binary for perfect TLS fingerprinting')
        print('Or: Run the Node.js puppeteer-extra backend which handles this natively')
    else:
        print('*** SWIGGY BYPASSED! ***')
        has_products = '₹' in content
        print(f'Has prices: {has_products}')
    
    await browser.stop()

asyncio.run(main())
