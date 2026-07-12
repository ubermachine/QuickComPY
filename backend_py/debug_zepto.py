import json
import re

def analyze():
    print("Analyzing zepto_loc.html...")
    with open('zepto_loc.html', 'r', encoding='utf-8') as f:
        html = f.read()
        
    # Search for json or script state containing location info
    # Zepto often uses NEXT_DATA or redxt/state
    next_data = re.search(r'<script id=\"__NEXT_DATA__\"[^>]*>(.*?)</script>', html)
    if next_data:
        print("Found __NEXT_DATA__!")
        try:
            data = json.loads(next_data.group(1))
            # Let's save a pretty print of NEXT_DATA keys
            with open("next_data_keys.json", "w") as f_out:
                json.dump(list(data.keys()), f_out, indent=2)
            print("Saved __NEXT_DATA__ keys.")
            
            # Let's look for address/location keys in the full next_data
            data_str = json.dumps(data)
            for term in ["address", "pincode", "latitude", "longitude", "city", "locality"]:
                found = [m.start() for m in re.finditer(term, data_str, re.IGNORECASE)]
                print(f"Term '{term}' found: {len(found)} times")
        except Exception as e:
            print("Error parsing __NEXT_DATA__:", e)
            
    # Search for local storage keys in scripts
    ls_matches = re.findall(r'localStorage\.setItem\([\'"]([^\'"]+)[\'"]', html)
    if ls_matches:
        print("localStorage.setItem keys found:", set(ls_matches))

if __name__ == "__main__":
    analyze()
