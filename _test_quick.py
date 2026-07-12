import sys, asyncio
sys.stdout.reconfigure(encoding='utf-8')
import zendriver as zd

async def test():
    # Try with anti-detection Chrome args
    config = zd.Config(
        sandbox=False,
        headless=True,
        args=[
            '--disable-blink-features=AutomationControlled',
            '--no-sandbox',
            '--disable-setuid-sandbox',
            '--disable-infobars',
            '--window-size=1920,1080',
            '--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36',
        ]
    )
    browser = await zd.start(config=config)
    
    for name, url in [('zepto', 'https://www.zepto.com/search?query=eggs'),
                       ('bigbasket', 'https://www.bigbasket.com/ps/?q=eggs')]:
        page = await browser.get(url, new_tab=True)
        await asyncio.sleep(5)
        content = await page.get_content()
        title = await page.evaluate('document.title') if len(content) > 100 else 'N/A'
        print(f'\n=== {name} ===')
        print(f'Title: {title}')
        print(f'Content: {len(content)} chars')
        if len(content) > 5000:
            print(f'Has prices: {"₹" in content}')
            print(f'Has product links: {"href" in content[:100000]}')
        else:
            print(f'Content: {content[:500]}')
        await page.close()
    
    await browser.stop()

asyncio.run(test())
