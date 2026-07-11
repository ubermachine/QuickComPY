const fs = require('fs');
const html = fs.readFileSync('instamart_search.html', 'utf-8');
const text = html.replace(/<style[^>]*>.*<\/style>/gi, '')
                 .replace(/<script[^>]*>.*<\/script>/gi, '')
                 .replace(/<[^>]+>/g, ' ')
                 .replace(/\s+/g, ' ')
                 .trim();
console.log(text.substring(0, 1000));
