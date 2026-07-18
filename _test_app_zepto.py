import asyncio
import sys
sys.path.append("streamlit")
from app import search_svc, run_set_location_all

async def main():
    print("Setting location...")
    res1 = await run_set_location_all('201301')
    print("Location results:", res1)
    print("Searching zepto...")
    res2 = await search_svc('zepto', 'eggs')
    print("Search results:", len(res2[1]))

if __name__ == "__main__":
    asyncio.run(main())
