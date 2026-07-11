const fs = require('fs');
const html = fs.readFileSync('instamart_search.html', 'utf8');
const regex = /data-testid="item-collection-card-full"/g;
const matches = html.match(regex);
console.log('Count:', matches ? matches.length : 0);
