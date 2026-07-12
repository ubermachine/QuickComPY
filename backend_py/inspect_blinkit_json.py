import json

def main():
    with open('blinkit_response.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    print('Keys:', list(data.keys()))
    if 'response' in data:
        resp = data['response']
        print('Response keys:', list(resp.keys()))
        if 'snippets' in resp:
            snippets = resp['snippets']
            print('Total snippets:', len(snippets))
            for idx, s in enumerate(snippets[:10]):
                print(f'Snippet {idx}: widget_type={s.get("widget_type")}, type={s.get("type")}')
                if 'data' in s:
                    print('  Data keys:', list(s["data"].keys()))
                    # Print details for first product
                    if s.get("type") == "product" or "product" in s.get("widget_type", ""):
                        print("  Sample product details:")
                        print("    name:", s["data"].get("name"))
                        print("    normal_price:", s["data"].get("normal_price"))
                        print("    price:", s["data"].get("price"))
                        print("    mrp:", s["data"].get("mrp"))
                        print("    variant:", s["data"].get("variant"))
                        print("    unit:", s["data"].get("unit"))
                        print("    identity:", s["data"].get("identity"))
                        break

if __name__ == "__main__":
    main()
