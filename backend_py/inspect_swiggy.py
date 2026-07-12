from html.parser import HTMLParser
import re

class SwiggyParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_card = False
        self.card_depth = 0
        self.current_card_html = []
        self.cards = []

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        # Check for card start
        if 'data-testid' in attrs_dict and 'item-collection-card' in attrs_dict['data-testid']:
            self.in_card = True
            self.card_depth = 0
            self.current_card_html = []
            
        if self.in_card:
            self.card_depth += 1
            # Reconstruct tag
            attrs_str = " ".join([f'{k}="{v}"' for k, v in attrs])
            self.current_card_html.append(f"<{tag} {attrs_str}>")

    def handle_endtag(self, tag):
        if self.in_card:
            self.current_card_html.append(f"</{tag}>")
            self.card_depth -= 1
            if self.card_depth == 0:
                self.in_card = False
                self.cards.append("".join(self.current_card_html))

    def handle_data(self, data):
        if self.in_card:
            self.current_card_html.append(data.strip())

def main():
    with open("instamart_search.html", "r", encoding="utf-8") as f:
        html = f.read()
        
    parser = SwiggyParser()
    parser.feed(html)
    
    print(f"Total cards parsed: {len(parser.cards)}")
    if parser.cards:
        print("\n--- SAMPLE CARD 1 ---")
        # Print first 2000 chars of the card HTML
        print(parser.cards[0][:2000])

if __name__ == "__main__":
    main()
