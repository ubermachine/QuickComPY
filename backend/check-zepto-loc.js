const puppeteer = require('puppeteer-extra');
const StealthPlugin = require('puppeteer-extra-plugin-stealth');
puppeteer.use(StealthPlugin());

async function checkLocationSelectors() {
  const browser = await puppeteer.launch({ headless: 'new', args: ['--no-sandbox'] });
  const page = await browser.newPage();
  await page.setUserAgent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36');
  
  await page.goto('https://www.zepto.com/', { waitUntil: 'domcontentloaded', timeout: 60000 });
  await new Promise(r => setTimeout(r, 5000));
  
  const report = await page.evaluate(function() {
    var selectors = [
      '[data-testid="user-address"]',
      '[data-testid="location-btn"]',
      '[data-testid="zepto-logo"]',
      '[class*="address"]',
      '[class*="location"]',
      '[class*="Location"]',
      '[class*="Address"]',
      'header button',
      '[placeholder="Search a new address"]',
      '[placeholder="Search"]',
      '[aria-label*="location"]',
      '[aria-label*="address"]'
    ];
    var found = {};
    for (var i = 0; i < selectors.length; i++) {
      var s = selectors[i];
      var els = document.querySelectorAll(s);
      if (els.length > 0) {
        found[s] = { count: els.length, text: els[0].textContent.trim().substring(0, 80) };
      }
    }
    var allTids = Array.from(document.querySelectorAll('[data-testid]'));
    var unique = [];
    var seen = {};
    allTids.forEach(function(e) {
      var t = e.getAttribute('data-testid');
      if (!seen[t]) { seen[t] = true; unique.push(t); }
    });
    found['__all_testids__'] = unique;
    return found;
  });
  
  console.log(JSON.stringify(report, null, 2));
  await browser.close();
}

checkLocationSelectors().catch(console.error);
