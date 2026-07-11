const fs = require('fs');
const jsdom = require('jsdom');
const { JSDOM } = jsdom;
const html = fs.readFileSync('instamart_search.html', 'utf8');
const dom = new JSDOM(html);
const document = dom.window.document;

const cards = document.querySelectorAll('[data-testid="item-collection-card-full"]');
const firstCard = cards[0];

console.log(firstCard.innerHTML);
