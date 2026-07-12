import re
import json
from curl_cffi.requests import AsyncSession

async def test_bb_location():
    url = "https://www.bigbasket.com/ps/?q=eggs"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }
    cookies = {
        "_bb_pin_code": "110001"
    }
    
    async with AsyncSession(impersonate="chrome110") as session:
        res = await session.get(url, headers=headers, cookies=cookies)
        
    match = re.search(r'window\.__PRELOADED_STATE__\s*=\s*(\{.*?\});', res.text)
    if match:
        state = json.loads(match.group(1))
        loc = state.get("searchState", {}).get("location")
        print("Bigbasket State Location info:", loc)
        products = state.get("searchState", {}).get("searchResult", {}).get("tabs", [{}])[0].get("product_info", {}).get("products", [])
        print("Found products:", len(products))
    else:
        print("Could not find PRELOADED_STATE. HTML length:", len(res.text))

import asyncio
if __name__ == "__main__":
    asyncio.run(test_bb_location())
