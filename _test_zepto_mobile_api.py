import urllib.request
import urllib.parse
import urllib.error

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
    'User-Agent': 'Zepto/10.0.0 (Android 11; okhttp/4.9.2)',
    'Accept': 'application/json',
    'appVersion': '16.15.0',
    'platform': 'ANDROID',
    'tenant': 'ZEPTO',
    'x-device-id': '87cb18e5-239a-4d3e-91a6-ca42d108800b'
}

endpoints = [
    "https://api.zeptonow.com/v1/search?query=milk",
    "https://api.zeptonow.com/v2/search?query=milk",
    "https://api.zeptonow.com/v3/search?query=milk",
    "https://bff-gateway.zepto.com/user-search-service/api/v3/search?query=milk&pageNumber=0"
]

for ep in endpoints:
    test_api(ep, headers)
