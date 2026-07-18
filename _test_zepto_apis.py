import urllib.request
import urllib.parse
import urllib.error
import json

def test_api(url, headers):
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req) as response:
            data = response.read().decode('utf-8')
            print(f"Success for {url}: {data[:500]}")
    except urllib.error.HTTPError as e:
        print(f"HTTP Error {e.code} for {url}: {e.read().decode('utf-8')[:200]}")
    except Exception as e:
        print(f"Error for {url}: {e}")

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Origin': 'https://www.zepto.com',
    'Referer': 'https://www.zepto.com/',
    'app_version': '16.15.0',
    'platform': 'WEB',
    'tenant': 'ZEPTO'
}

endpoints = [
    "https://api.zeptonow.com/v1/search?query=milk",
    "https://api.zeptonow.com/v2/search?query=milk",
    "https://api.zeptonow.com/v3/search?query=milk",
    "https://bff-gateway.zepto.com/user-search-service/api/v3/search?query=milk&pageNumber=0",
    "https://bff-gateway.zepto.com/user-search-service/api/v3/search?q=milk"
]

for ep in endpoints:
    test_api(ep, headers)
