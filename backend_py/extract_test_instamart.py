from bs4 import BeautifulSoup
import json

def extract():
    with open('instamart_all.html', 'r', encoding='utf-8') as f:
        soup = BeautifulSoup(f.read(), 'html.parser')
        
    titles = soup.find_all(class_='_1lbNR')
    print('Found titles:', len(titles))
    
    products = []
    for t in titles:
        # Walk up 5 levels to get the container (which we saw was _1WDPG)
        # title -> div -> div._3Rr1X -> div.sWdPz -> div -> div._1WDPG
        parent = t.parent.parent.parent.parent.parent
        card = parent
        
        name = t.text.strip()
        
        price_el = card.find(class_='_2jn41')
        price = price_el.text.strip() if price_el else 'N/A'
        
        qty_el = card.find(class_='_3wq_F')
        quantity = qty_el.text.strip() if qty_el else '1 item'
        
        img_el = card.find('img', class_='_16I1D')
        img_url = img_el.get('src') if img_el else ''
        
        products.append({
            'name': name,
            'price': price,
            'quantity': quantity,
            'img_url': img_url[:30] + '...' if img_url else ''
        })
        
    print(f"Extracted {len(products)} products:")
    for p in products[:5]:
        print(p)

if __name__ == "__main__":
    extract()
