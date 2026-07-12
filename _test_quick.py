import sys, json
sys.stdout.reconfigure(encoding='utf-8')

from curl_cffi import requests
from backend_py.awswaf.aws import AwsWaf

session = requests.Session(impersonate='chrome')
session.headers.update({
    'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'accept-language': 'en-US,en;q=0.9',
    'cache-control': 'no-cache',
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/136.0.0.0 Safari/537.36',
    'sec-ch-ua': '"Chromium";v="136", "Google Chrome";v="136", "Not.A/Brand";v="99"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"',
})

print('Fetching Swiggy Instamart homepage...')
resp = session.get('https://www.swiggy.com/instamart', timeout=30)
print(f'Status: {resp.status_code}')

goku, host = AwsWaf.extract(resp.text)
print(f'Challenge type: {goku.get("challenge_type", "unknown")}')
print(f'Host: {host}')
print(f'Full goku keys: {list(goku.keys())}')

# Now also fetch the inputs endpoint to see what challenge type it uses
inputs_resp = session.get(f'https://{host}/inputs?client=browser', timeout=30)
print(f'\nInputs status: {inputs_resp.status_code}')
print(f'Inputs: {json.dumps(inputs_resp.json(), indent=2)[:1000]}')
