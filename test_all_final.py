import sys, asyncio, json
sys.stdout.reconfigure(encoding='utf-8')

import zendriver as zd
from backend_py.scrapers import blinkit, bigbasket, jiomart, zepto, instamart

async def test_all():
    browser = await zd.start(config=zd.Config(sandbox=False, headless=True))
    results = {}
    try:
        for name, mod in [
            ('blinkit', blinkit),
            ('bigbasket', bigbasket),
            ('jiomart', jiomart),
            ('zepto', zepto),
            ('instamart', instamart),
        ]:
            page = await browser.get('about:blank', new_tab=True)
            try:
                loc_ok = await asyncio.wait_for(mod.set_location(page, '110001'), timeout=15.0)
                products = await asyncio.wait_for(mod.search(page, 'eggs'), timeout=30.0)
                details = {}
                if products:
                    p = products[0]
                    details = {k: v for k, v in p.items() if k != 'imageUrl'}
                results[name] = {
                    'location': loc_ok,
                    'count': len(products),
                    'sample': details,
                }
                sources = set(p.get('source') for p in products)
                print(f'[{name}] loc={loc_ok} products={len(products)} sources={sources}')
                if details:
                    print(f'  Sample: {json.dumps(details, ensure_ascii=False)[:300]}')
            except asyncio.TimeoutError:
                print(f'[{name}] TIMEOUT')
                results[name] = {'location': False, 'count': -1}
            except Exception as e:
                print(f'[{name}] ERROR: {type(e).__name__}: {e}')
                results[name] = {'location': False, 'count': -2, 'error': str(e)[:100]}
            finally:
                await page.close()
    finally:
        await browser.stop()
    
    print(f'\n{"="*60}')
    print('FINAL RESULTS:')
    print(json.dumps(results, indent=2, ensure_ascii=False))
    
    working = sum(1 for r in results.values() if r.get('count', 0) > 0)
    print(f'\n{working}/5 scrapers returning products')

asyncio.run(test_all())
