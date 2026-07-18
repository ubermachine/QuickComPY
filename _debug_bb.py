"""Debug Bigbasket - find why candidates are 0"""
import sys, asyncio, zendriver as zd
sys.stdout.reconfigure(encoding='utf-8')
_STEALTH = """Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
Object.defineProperty(navigator, 'plugins', { get: () => [1,2,3,4,5] });
Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
window.chrome = { runtime: {} };"""

async def main():
    config = zd.Config(sandbox=False, headless=True)
    browser = await zd.start(config=config)
    page = await browser.get("about:blank", new_tab=True)
    await page.send(zd.cdp.page.add_script_to_evaluate_on_new_document(source=_STEALTH))
    
    from backend_py.scrapers import bigbasket
    await bigbasket.set_location(page, "110001")
    await page.get("https://www.bigbasket.com/ps/?q=milk")
    await asyncio.sleep(6)
    
    info = await page.evaluate("""
    (function() {
        var items = document.querySelectorAll('li');
        var result = [];
        for (var i = 0; i < items.length; i++) {
            var li = items[i];
            var text = (li.textContent || '').replace(/\\s+/g, ' ').trim();
            if (text.indexOf('\\u20B9') < 0) continue;
            var img = li.querySelector('img');
            result.push({
                idx: i,
                textLen: text.length,
                hasImg: !!img,
                imgCount: li.querySelectorAll('img').length,
                imgSrc: img ? (img.src || '').substring(0, 80) : 'none',
                textStart: text.substring(0, 60)
            });
        }
        // Count items that have both img + price
        var withImg = 0;
        for (var j = 0; j < result.length; j++) {
            if (result[j].hasImg) withImg++;
        }
        return {totalWithPrice: result.length, totalWithImg: withImg, samples: result.slice(0, 8)};
    })()
    """)
    
    print(f"Total <li> with ₹: {info['totalWithPrice']}")
    print(f"With image: {info['totalWithImg']}")
    for s in info['samples']:
        print(f"  [{s['idx']}] len={s['textLen']} img={s['hasImg']} cnt={s['imgCount']}")
        print(f"        text: {s['textStart']}")
        print(f"        src: {s['imgSrc'][:60]}")
    
    await browser.stop()
asyncio.run(main())
