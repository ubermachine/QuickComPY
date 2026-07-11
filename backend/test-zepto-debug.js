/**
 * test-zepto-debug.js
 * Navigate to zeptonow.com, intercept all XHR/fetch/GraphQL requests during
 * a search and log API URLs + product response structures.
 *
 * Usage:  node test-zepto-debug.js
 */

const puppeteer = require('puppeteer-extra');
const StealthPlugin = require('puppeteer-extra-plugin-stealth');
puppeteer.use(StealthPlugin());

const SEARCH_QUERY = 'milk';

/* ────────────────────────────────────────────────────── helpers ─── */

function tryParse(text) {
  try { return JSON.parse(text); } catch { return null; }
}

function preview(obj) {
  try {
    return JSON.stringify(obj, null, 2)
      .split('\n').slice(0, 60).join('\n');
  } catch { return String(obj); }
}

/** Walk JSON and look for arrays that look like product lists */
function findProductArrays(obj, path, results) {
  path = path || '';
  results = results || [];
  if (!obj || typeof obj !== 'object') return results;
  if (Array.isArray(obj)) {
    if (obj.length > 0 && obj[0] && typeof obj[0] === 'object') {
      const sample = obj[0];
      const keys = Object.keys(sample).join(' ');
      if (/name|title|product|item|sku|mrp|price/i.test(keys)) {
        results.push({ path: path, length: obj.length, sample: sample });
      }
    }
    obj.forEach(function(v, i) { findProductArrays(v, path + '[' + i + ']', results); });
  } else {
    Object.entries(obj).forEach(function(kv) {
      findProductArrays(kv[1], path + '.' + kv[0], results);
    });
  }
  return results;
}

/* ────────────────────────────────────────────────────── main ────── */

async function main() {
  console.log('='.repeat(60));
  console.log('Zepto Network Debug – Search term:', SEARCH_QUERY);
  console.log('='.repeat(60));

  const browser = await puppeteer.launch({
    headless: 'new',
    args: [
      '--no-sandbox',
      '--disable-setuid-sandbox',
      '--disable-blink-features=AutomationControlled',
    ],
  });

  const page = await browser.newPage();
  await page.setViewport({ width: 1366, height: 768 });
  await page.setUserAgent(
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) ' +
    'AppleWebKit/537.36 (KHTML, like Gecko) ' +
    'Chrome/124.0.0.0 Safari/537.36'
  );

  /* ── intercept every request ───────────────────────────────────── */
  const intercepted = [];

  await page.setRequestInterception(true);
  page.on('request', function(req) {
    req.continue();
  });

  page.on('response', async function(response) {
    const url    = response.url();
    const method = response.request().method();
    const type   = response.request().resourceType();
    const status = response.status();

    // Only care about data requests
    if (!['xhr', 'fetch', 'document'].includes(type)) return;
    // Skip static assets
    if (/\.(png|jpg|jpeg|gif|svg|webp|ico|woff|woff2|ttf|css|js)(\?|$)/i.test(url)) return;

    let body = null;
    let productPaths = [];
    try {
      const text = await response.text();
      body = tryParse(text);
      if (body) productPaths = findProductArrays(body);

      intercepted.push({ url: url, method: method, type: type, status: status, body: body, productPaths: productPaths });

      const marker = productPaths.length > 0 ? '>>> PRODUCTS FOUND <<<' : '    ';
      console.log('\n' + marker + ' [' + type.toUpperCase() + '] ' + method + ' ' + status + ' ' + url.substring(0, 120));
      if (productPaths.length > 0) {
        productPaths.forEach(function(p) {
          console.log('  path:', p.path, '  count:', p.length);
          console.log('  keys:', Object.keys(p.sample).join(', '));
          console.log('  sample:\n', preview(p.sample));
        });
      }
    } catch (e) {
      // binary/non-JSON
    }
  });

  /* ── Step 1: homepage ──────────────────────────────────────────── */
  console.log('\n[1] Navigating to https://www.zeptonow.com ...');
  try {
    await page.goto('https://www.zeptonow.com', {
      waitUntil: 'domcontentloaded',
      timeout: 60000,
    });
  } catch (e) {
    console.log('  goto warning:', e.message);
  }
  await new Promise(function(r) { setTimeout(r, 4000); });

  const homeTitle = await page.title().catch(function() { return '(no title)'; });
  const homeURL   = page.url();
  console.log('  title:', homeTitle);
  console.log('  url:  ', homeURL);

  /* ── Step 2: broken URL that returns 404 ──────────────────────── */
  console.log('\n[2] Testing broken URL: https://www.zepto.com/srp?q=' + SEARCH_QUERY);
  try {
    await page.goto('https://www.zepto.com/srp?q=' + SEARCH_QUERY, {
      waitUntil: 'domcontentloaded',
      timeout: 30000,
    });
  } catch (e) {
    console.log('  goto warning:', e.message);
  }
  await new Promise(function(r) { setTimeout(r, 3000); });
  const srpTitle = await page.title().catch(function() { return '(no title)'; });
  const srpURL   = page.url();
  console.log('  title:', srpTitle);
  console.log('  url:  ', srpURL);

  /* ── Step 3: correct search URL ───────────────────────────────── */
  const searchURL = 'https://www.zeptonow.com/search?query=' + encodeURIComponent(SEARCH_QUERY);
  console.log('\n[3] Navigating to: ' + searchURL);
  try {
    await page.goto(searchURL, {
      waitUntil: 'domcontentloaded',
      timeout: 60000,
    });
  } catch (e) {
    console.log('  goto warning:', e.message);
  }
  await new Promise(function(r) { setTimeout(r, 6000); });

  const searchTitle  = await page.title().catch(function() { return '(no title)'; });
  const searchPageURL = page.url();
  console.log('  title:', searchTitle);
  console.log('  url:  ', searchPageURL);

  /* ── Step 4: HTML product indicators ─────────────────────────── */
  console.log('\n[4] Inspecting HTML for product indicators ...');
  const htmlReport = await page.evaluate(function() {
    var testIds = [
      '[data-testid="product-card"]',
      '[data-testid="product-card-name"]',
      '[data-testid="product-card-image"]',
    ];
    var result = {};
    for (var i = 0; i < testIds.length; i++) {
      result[testIds[i]] = document.querySelectorAll(testIds[i]).length;
    }
    result['a[href*="/pn/"]'] = document.querySelectorAll('a[href*="/pn/"]').length;
    result['[class*="product"]'] = document.querySelectorAll('[class*="product"]').length;
    result['[class*="ProductCard"]'] = document.querySelectorAll('[class*="ProductCard"]').length;
    result['has_404'] = document.body.innerText.includes('404') ||
                        document.body.innerText.toLowerCase().includes('page not found');
    result['body_snippet'] = document.body.innerText.substring(0, 500);
    var all = Array.from(document.querySelectorAll('[data-testid]'));
    var unique = [];
    var seen = {};
    all.forEach(function(el) {
      var tid = el.getAttribute('data-testid');
      if (!seen[tid]) { seen[tid] = true; unique.push(tid); }
    });
    result['all_testids'] = unique.slice(0, 30);
    return result;
  });
  console.log(JSON.stringify(htmlReport, null, 2));

  /* ── Step 5: scroll to trigger lazy loads ─────────────────────── */
  console.log('\n[5] Scrolling to trigger lazy-loaded content ...');
  await page.evaluate(function() { window.scrollBy(0, 800); });
  await new Promise(function(r) { setTimeout(r, 3000); });
  await page.evaluate(function() { window.scrollBy(0, 800); });
  await new Promise(function(r) { setTimeout(r, 2000); });

  /* ── Final report ─────────────────────────────────────────────── */
  console.log('\n' + '='.repeat(60));
  console.log('INTERCEPT SUMMARY');
  console.log('='.repeat(60));

  var withProducts = intercepted.filter(function(r) { return r.productPaths.length > 0; });

  console.log('\nTotal intercepted requests:', intercepted.length);
  console.log('Requests with product arrays:', withProducts.length);

  console.log('\n-- All XHR/Fetch/Document URLs intercepted --');
  intercepted.forEach(function(r) {
    console.log(' [' + r.status + '] ' + r.method + ' ' + r.url);
  });

  if (withProducts.length > 0) {
    console.log('\n-- Requests WITH PRODUCT DATA --');
    withProducts.forEach(function(r) {
      console.log('\n  URL:', r.url);
      r.productPaths.forEach(function(p) {
        console.log('  path:', p.path);
        console.log('  count:', p.length);
        console.log('  fields:', Object.keys(p.sample).join(', '));
        console.log('  sample:\n', preview(p.sample));
      });
    });
  } else {
    console.log('\n[WARNING] No product data found in any intercepted response.');
    console.log('    The site may require a location cookie or bot-detection is blocking.');
    console.log('\n-- Full response bodies for non-image XHR/fetch --');
    intercepted.slice(0, 10).forEach(function(r) {
      console.log('\n  [' + r.status + '] ' + r.url);
      if (r.body) {
        console.log('  body preview:', preview(r.body));
      }
    });
  }

  await browser.close();
  console.log('\n[Done]');
}

main().catch(function(err) {
  console.error('Fatal error:', err);
  process.exit(1);
});
