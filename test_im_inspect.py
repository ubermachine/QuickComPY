import json

with open("im_api_dump.json", "r", encoding="utf-8") as f:
    d = json.load(f)

cards = d["data"]["cards"]
print(f"Total cards: {len(cards)}\n")

for i, c in enumerate(cards):
    card = c.get("card", {}).get("card", c.get("card", {}))
    card_type = card.get("@type", "unknown")
    print(f"Card {i}: type={card_type}")
    
    # Check for gridElements which usually contain products
    if "gridElements" in card:
        ge = card["gridElements"]
        print(f"  gridElements keys: {list(ge.keys())}")
        info_grid = ge.get("infoWithStyle", {})
        if info_grid:
            print(f"  infoWithStyle keys: {list(info_grid.keys())}")
            products = info_grid.get("products", info_grid.get("info", []))
            if products and isinstance(products, list):
                print(f"  Found {len(products)} products!")
                if len(products) > 0:
                    p = products[0]
                    if isinstance(p, dict):
                        print(f"  First product keys: {list(p.keys())}")
                        # Go one more level
                        for k in ["displayName", "name", "price", "product_info", "productId"]:
                            if k in p:
                                print(f"    {k}: {str(p[k])[:100]}")
    elif "title" in card:
        print(f"  title: {card.get('title', '')}")
    print()
