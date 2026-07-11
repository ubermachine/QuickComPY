/**
 * test-instamart-debug.js
 * Discover correct selectors on Swiggy Instamart.
 * Uses puppeteer-extra + stealth. No screenshots - HTML + network inspection only.
 */
const puppeteer = require('puppeteer-extra');
const StealthPlugin = require('puppeteer-extra-plugin-stealth');
puppeteer.use(StealthPlugin());
const fs = require('fs');

async function debugInstamart() {
  console.log('=== Instamart Selector Debug ===\n');

  const browser = await puppeteer.launch({
    headless: 'new',
    args: ['--no-sandbox','--disable-setuid-sandbox','--disable-blink-features=AutomationControlled','--window-size=1280,800']
  });

  const page = await browser.newPage();
  await page.setViewport({ width: 1280, height: 800 });
  await page.setUserAgent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36');

  // Network interception
  const interceptedAPIs = [];
  let productAPIResponse = null;
  page.on('response', async (response) => {
    const url = response.url();
    const ct = response.headers()['content-type'] || '';
    if (!ct.includes('json')) return;
    if (url.includes('/api/') || url.includes('/mapi/') || url.includes('search') || url.includes('listing') || url.includes('instamart')) {
      try {
        const json = await response.json();
        const entry = { url, status: response.status(), keys: json ? Object.keys(json) : [] };
        interceptedAPIs.push(entry);
        if (json && (json.data || json.statusCode === 0)) {
          console.log('[API]', url.slice(0, 120));
          console.log('  keys:', Object.keys(json).join(', '));
          const str = JSON.stringify(json).toLowerCase();
          if (str.includes('"name"') && (str.includes('"price"') || str.includes('"mrp"'))) {
            console.log('  *** Likely product response! Saving debug-api-response.json ***');
            productAPIResponse = json;
            fs.writeFileSync('debug-api-response.json', JSON.stringify(json, null, 2));
          }
        }
      } catch (_) {}
    }
  });

  // STEP 1: Navigate to Swiggy Instamart home
  console.log('[STEP 1] Navigating to https://www.swiggy.com/instamart ...');
  try {
    await page.goto('https://www.swiggy.com/instamart', { waitUntil: 'networkidle2', timeout: 60000 });
  } catch (e) {
    console.log('  networkidle2 timed out, continuing:', e.message);
  }
  await new Promise(r => setTimeout(r, 4000));
  console.log('  Current URL:', page.url());

  // STEP 2: Scan all data-testid on home page
  console.log('\n[STEP 2] data-testid attributes on home page...');
  const homeTestIds = await page.evaluate(() => {
    const map = {};
    document.querySelectorAll('[data-testid]').forEach(el => {
      const tid = el.getAttribute('data-testid');
      if (!map[tid]) map[tid] = { tag: el.tagName.toLowerCase(), text: el.textContent.trim().slice(0, 60), cls: el.className.slice(0, 80), count: 0 };
      map[tid].count++;
    });
    return map;
  });
  Object.entries(homeTestIds).forEach(([tid, info]) => {
    console.log('  [' + info.count + 'x] testid="' + tid + '" <' + info.tag + '> text="' + info.text + '"');
  });

  // STEP 3: Location-related selectors
  console.log('\n[STEP 3] Location/address related elements...');
  const locInfo = await page.evaluate(() => {
    const results = [];
    const kwds = ['location', 'address', 'deliver', 'pincode', 'area'];
    document.querySelectorAll('*').forEach(el => {
      const cls = (el.className && typeof el.className === 'string' ? el.className : '').toLowerCase();
      const tid = (el.getAttribute && el.getAttribute('data-testid') || '').toLowerCase();
      const txt = el.textContent ? el.textContent.trim().slice(0, 60) : '';
      if (kwds.some(k => cls.includes(k) || tid.includes(k)) && txt.length > 0) {
        results.push({ tag: el.tagName.toLowerCase(), cls: (el.className || '').slice(0, 80), tid: el.getAttribute('data-testid') || '', txt });
      }
    });
    return results.slice(0, 30);
  });
  locInfo.forEach(r => console.log('  <' + r.tag + '> tid="' + r.tid + '" cls="' + r.cls + '" txt="' + r.txt + '"'));

  // STEP 4: All inputs on home page
  console.log('\n[STEP 4] All inputs on home page...');
  const inputs = await page.evaluate(() =>
    Array.from(document.querySelectorAll('input')).map(el => ({
      type: el.type, placeholder: el.getAttribute('placeholder') || '',
      name: el.name, id: el.id, cls: el.className.slice(0, 80), visible: el.offsetParent !== null
    }))
  );
  inputs.forEach(i => console.log('  input[' + i.type + '] placeholder="' + i.placeholder + '" name="' + i.name + '" visible=' + i.visible + ' cls="' + i.cls + '"'));

  // STEP 5: Save home HTML
  console.log('\n[STEP 5] Saving debug-home.html ...');
  fs.writeFileSync('debug-home.html', await page.content());
  console.log('  Saved.');

  // STEP 6: Navigate to search page
  console.log('\n[STEP 6] Navigating to search for "milk" ...');
  try {
    await page.goto('https://www.swiggy.com/instamart/search?query=milk', { waitUntil: 'networkidle2', timeout: 60000 });
  } catch (e) {
    console.log('  networkidle2 timed out:', e.message);
  }
  await new Promise(r => setTimeout(r, 5000));
  console.log('  Current URL:', page.url());

  // STEP 7: Scan all data-testid on search page
  console.log('\n[STEP 7] data-testid values on search page...');
  const searchTestIds = await page.evaluate(() => {
    const map = {};
    document.querySelectorAll('[data-testid]').forEach(el => {
      const tid = el.getAttribute('data-testid');
      if (!map[tid]) map[tid] = { tag: el.tagName.toLowerCase(), text: el.textContent.trim().slice(0, 80), cls: el.className.slice(0, 80), count: 0 };
      map[tid].count++;
    });
    return map;
  });
  Object.entries(searchTestIds).forEach(([tid, info]) => {
    console.log('  [' + info.count + 'x] testid="' + tid + '" <' + info.tag + '> text="' + info.text + '"');
  });

  // STEP 8: Product card candidates
  console.log('\n[STEP 8] Product card candidate selectors...');
  const cardSelectors = [
    '[data-testid*="product"]','[data-testid*="item"]','[data-testid*="card"]',
    '[data-testid*="container"]','[data-testid*="ux4"]','[data-testid*="UX4"]',
    '[class*="ProductCard"]','[class*="product-card"]','[class*="ItemCard"]',
    '[class*="ux4"]','[class*="XjYJe"]','[class*="_179Mx"]','[class*="novMV"]',
    'li[class*="sc-"]','div[class*="sc-"]'
  ];
  const cardResults = await page.evaluate((selectors) => {
    return selectors.map(sel => {
      const els = document.querySelectorAll(sel);
      if (els.length === 0) return null;
      const first = els[0];
      return {
        selector: sel, count: els.length,
        classes: first.className.slice(0, 100),
        text: first.innerText ? first.innerText.slice(0, 150).replace(/\n/g, ' | ') : '',
        testid: first.getAttribute('data-testid') || ''
      };
    }).filter(Boolean);
  }, cardSelectors);
  cardResults.forEach(c => {
    console.log('  [' + c.count + 'x]', c.selector);
    console.log('    testid="' + c.testid + '" classes="' + c.classes + '"');
    console.log('    text="' + c.text + '"');
  });

  // STEP 9: Price text scan
  console.log('\n[STEP 9] Price-like text elements...');
  const priceEls = await page.evaluate(() => {
    const results = [];
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    let node;
    while ((node = walker.nextNode())) {
      const text = node.textContent.trim();
      if (text.includes('\u20B9') || /^\d+(\.\d+)?$/.test(text)) {
        const parent = node.parentElement;
        if (parent && parent !== document.body) {
          results.push({ text, tag: parent.tagName.toLowerCase(), cls: parent.className.slice(0, 80), testid: parent.getAttribute('data-testid') || '' });
        }
      }
    }
    return results.slice(0, 40);
  });
  priceEls.forEach(r => console.log('  "' + r.text + '" in <' + r.tag + '> testid="' + r.testid + '" cls="' + r.cls + '"'));

  // STEP 10: Body text preview
  console.log('\n[STEP 10] Page body text preview:');
  const bodyText = await page.evaluate(() => document.body.innerText.slice(0, 600));
  console.log(bodyText);

  // STEP 11: Save search HTML
  console.log('\n[STEP 11] Saving debug-search.html ...');
  fs.writeFileSync('debug-search.html', await page.content());
  console.log('  Saved.');

  // STEP 12: Intercepted APIs
  console.log('\n[STEP 12] All intercepted JSON API calls:');
  interceptedAPIs.forEach(api => {
    console.log('  [' + api.status + ']', api.url.slice(0, 120));
    if (api.keys.length) console.log('    keys:', api.keys.join(', '));
  });

  await browser.close();
  console.log('\n=== Debug complete ===');
}

debugInstamart().catch(err => { console.error('Fatal:', err); process.exit(1); });
