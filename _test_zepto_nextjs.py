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
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Origin': 'https://www.zepto.com',
    'Referer': 'https://www.zepto.com/',
}

test_api("https://www.zepto.com/_next/data/16.15.0/search.json?query=milk", headers)
