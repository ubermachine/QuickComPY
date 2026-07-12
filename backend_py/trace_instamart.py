from bs4 import BeautifulSoup
import json

def trace():
    with open('instamart_all.html', 'r', encoding='utf-8') as f:
        soup = BeautifulSoup(f.read(), 'html.parser')
        
    first = soup.find(class_='_1lbNR')
    current = first
    path = []
    while current and current.name != 'body':
        classes = current.get('class', [])
        path.append(f"{current.name}.{'.'.join(classes)}")
        current = current.parent
        
    print('Path to title:')
    for p in path:
        print(" ->", p)

if __name__ == "__main__":
    trace()
