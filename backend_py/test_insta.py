import asyncio
import zendriver as zd

async def main():
    browser = await zd.start(config=zd.Config(sandbox=False, headless=True))
    try:
        page = await browser.get('about:blank', new_tab=True)
        from backend_py.scrapers import instamart
        await instamart.set_location(page, "bangalore")
        await asyncio.sleep(2)
        products = await instamart.search(page, "milk")
        print(f"Instamart products found: {len(products)}")
        if products:
            print("First product name:", products[0]['name'])
    finally:
        await browser.stop()

if __name__ == "__main__":
    asyncio.run(main())
