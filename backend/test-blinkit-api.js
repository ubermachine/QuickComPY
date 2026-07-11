/**
 * test-blinkit-api.js
 *
 * Purpose: Intercept ALL network requests made by blinkit.com during:
 *   1. Homepage load (to find location/session APIs)
 *   2. Location-setting flow (to find the location-set API)
 *   3. Search flow (to find the product-search API)
 *
 * Strategy:
 *   - Use puppeteer-extra + stealth to avoid bot detection
 *   - Intercept every XHR/fetch response, log URL + status + first 2KB of body
 *   - Focus on api.blinkit.com or any JSON response with product-like data
 *   - No screenshots — only console logs and saved JSON files
 */

const puppeteer = require('puppeteer-extra');
const StealthPlugin = require('puppeteer-extra-plugin-stealth');
const fs = require('fs');
const path = require('path');

puppeteer.use(StealthPlugin());

// ─────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────

const OUT_DIR = path.join(__dirname, 'blinkit_api_dump');
if (!fs.existsSync(OUT_DIR)) fs.mkdirSync(OUT_DIR, { recursive: true });

let requestLog = [];    // all intercepted API calls
let productJson = null; // first response that looks like search results
let locationJson = null; // response that looks like location set confirmation

function saveJson(filename, data) {
  const fp = path.join(OUT_DIR, filename);
  fs.writeFileSync(fp, JSON.stringify(data, null, 2), 'utf8');
  console.log(`[SAVED] ${fp}`);
}

function looksLikeProducts(json) {
  // Blinkit search response structure (known from searchHelpers.js)
  if (json && json.response && Array.isArray(json.response.snippets) && json.response.snippets.length > 0) return true;
  // Alternative: array of objects with name/price fields
  if (Array.isArray(json) && json.length > 0 && json[0] && (json[0].name || json[0].product_name)) return true;
  // objects.widgets / objects.data patterns
  if (json && json.data && Array.isArray(json.data.objects)) return true;
  if (json && Array.isArray(json.objects)) return true;
  return false;
}

function looksLikeLocation(url, json) {
  const u = url.toLowerCase();
  if (u.includes('location') || u.includes('locality') || u.includes('address') || u.includes('geocode') || u.includes('serviceable')) return true;
  if (json && (json.lat !== undefined || json.latitude !== undefined || json.pincode !== undefined)) return true;
  if (json && json.data && (json.data.lat !== undefined || json.data.locality !== undefined)) return true;
  return false;
}

// ─────────────────────────────────────────────
// Main
// ─────────────────────────────────────────────

async function main() {
  console.log('='.repeat(60));
  console.log('Blinkit API Intercept Test');
  console.log('='.repeat(60));

  const browser = await puppeteer.launch({
    headless: 'new',
    args: [
      '--no-sandbox',
      '--disable-setuid-sandbox',
      '--disable-blink-features=AutomationControlled',
      '--disable-dev-shm-usage',
      '--window-size=1280,900',
    ],
  });

  const page = await browser.newPage();

  // Realistic viewport & UA
  await page.setViewport({ width: 1280, height: 900 });
  await page.setUserAgent(
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36'
  );

  // Extra headers to look like a real browser
  await page.setExtraHTTPHeaders({
    'Accept-Language': 'en-IN,en;q=0.9',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
  });

  // ── Intercept ALL responses ──────────────────
  page.on('response', async (response) => {
    const url = response.url();
    const status = response.status();
    const contentType = response.headers()['content-type'] || '';

    // Only care about JSON/API responses (not images, fonts, css)
    const isApi = (
      url.includes('api.blinkit.com') ||
      url.includes('blinkit.com/v') ||
      url.includes('/search') ||
      url.includes('/location') ||
      url.includes('/locality') ||
      url.includes('/autocomplete') ||
      url.includes('/products') ||
      url.includes('/catalog') ||
      contentType.includes('application/json')
    );

    if (!isApi) return;

    let body = null;
    let json = null;
    try {
      body = await response.text();
      if (contentType.includes('application/json') || body.trim().startsWith('{') || body.trim().startsWith('[')) {
        json = JSON.parse(body);
      }
    } catch (_) {
      // keep body as string
    }

    const entry = {
      url,
      status,
      contentType,
      bodyPreview: body ? body.slice(0, 500) : null,
    };
    requestLog.push(entry);

    console.log(`\n[API] ${status} ${url}`);
    if (body) console.log(`  Preview: ${body.slice(0, 300)}`);

    if (json && looksLikeProducts(json) && !productJson) {
      console.log(`  *** PRODUCT DATA FOUND ***`);
      productJson = { url, json };
      saveJson('product_response.json', { url, json });
    }

    if (json && looksLikeLocation(url, json) && !locationJson) {
      console.log(`  *** LOCATION DATA FOUND ***`);
      locationJson = { url, json };
      saveJson('location_response.json', { url, json });
    }
  });

  // ── PHASE 1: Load homepage ──────────────────
  console.log('\n[PHASE 1] Loading homepage...');
  try {
    await page.goto('https://blinkit.com/', {
      waitUntil: 'networkidle2',
      timeout: 60000,
    });
  } catch (e) {
    console.log(`  goto error (may be ok): ${e.message}`);
  }
  await delay(3000);

  // Check for bot detection / Cloudflare
  const htmlSnippet = await page.evaluate(() => document.body ? document.body.innerHTML.slice(0, 1000) : '');
  console.log('\n[PAGE HTML PREVIEW]', htmlSnippet);

  // ── PHASE 2: Trigger location search via URL params ──────────────────
  // Blinkit uses lat/lon in localStorage or cookies; try to find location API
  console.log('\n[PHASE 2] Attempting location set via URL...');
  // Try navigating with lat/lon query params (common Blinkit pattern)
  try {
    await page.goto('https://blinkit.com/?lat=28.6139&lon=77.2090', {
      waitUntil: 'networkidle2',
      timeout: 30000,
    });
  } catch (e) {
    console.log(`  goto error: ${e.message}`);
  }
  await delay(3000);

  // ── PHASE 3: Intercept location API by triggering the search box ──────────────────
  console.log('\n[PHASE 3] Attempting location autocomplete API intercept...');
  // Look for the locality input and type in it to trigger autocomplete API
  const locInputSel = '[name="select-locality"], input[placeholder*="location" i], input[placeholder*="area" i], input[placeholder*="pincode" i]';
  try {
    const locInput = await page.$(locInputSel);
    if (locInput) {
      await locInput.click();
      await delay(500);
      await page.keyboard.type('Connaught', { delay: 80 });
      await delay(3000); // wait for autocomplete API call
      console.log('  Typed location, waiting for autocomplete...');
    } else {
      console.log('  Location input not found, trying XHR directly...');
      // Manually call the location API via fetch within the page context
      const locationApiResult = await page.evaluate(async () => {
        try {
          const res = await fetch('https://api.blinkit.com/v1/locality/search?q=Connaught+Place&lat=28.6139&lon=77.2090', {
            credentials: 'include',
            headers: { 'Accept': 'application/json' }
          });
          return { status: res.status, body: await res.text() };
        } catch (e) {
          return { error: e.message };
        }
      });
      console.log('  Location API direct call:', JSON.stringify(locationApiResult).slice(0, 500));
    }
  } catch (e) {
    console.log(`  Location phase error: ${e.message}`);
  }

  // ── PHASE 4: Try known Blinkit API endpoints directly ──────────────────
  console.log('\n[PHASE 4] Probing known Blinkit API endpoints...');
  const knownEndpoints = [
    'https://api.blinkit.com/v1/layout/listing?search_string=milk&latitude=28.6139&longitude=77.2090',
    'https://api.blinkit.com/v2/listing/search?search_string=milk&lat=28.6139&lon=77.2090',
    'https://blinkit.com/v6/search/listing/?search_string=milk&lat=28.6139&lon=77.2090',
    'https://blinkit.com/v1/catalog/search?q=milk',
    'https://api.blinkit.com/v2/search?q=milk&lat=28.6139&lon=77.2090',
    'https://api.blinkit.com/v1/listing?search_string=milk&lat=28.6139&lon=77.2090',
  ];

  for (const endpoint of knownEndpoints) {
    const result = await page.evaluate(async (url) => {
      try {
        const res = await fetch(url, {
          credentials: 'include',
          headers: {
            'Accept': 'application/json, text/plain, */*',
            'app_version': '3.0',
            'web_app_version': '1000000',
          }
        });
        const text = await res.text();
        return { status: res.status, body: text.slice(0, 800) };
      } catch (e) {
        return { error: e.message };
      }
    }, endpoint);
    console.log(`\n  Probed: ${endpoint}`);
    console.log(`  Result: ${JSON.stringify(result).slice(0, 600)}`);
  }

  // ── PHASE 5: Navigate to search page and intercept ──────────────────
  console.log('\n[PHASE 5] Navigating to search page for "milk"...');
  try {
    await page.goto('https://blinkit.com/s/?q=milk', {
      waitUntil: 'networkidle2',
      timeout: 60000,
    });
  } catch (e) {
    console.log(`  goto error: ${e.message}`);
  }
  await delay(5000);

  const searchHtmlSnippet = await page.evaluate(() => document.body ? document.body.innerHTML.slice(0, 1000) : '');
  console.log('\n[SEARCH PAGE HTML PREVIEW]', searchHtmlSnippet);

  // ── PHASE 6: Try intercepting via page.setRequestInterception + modify ──────────────────
  // Try fetching search API from within the page context (has cookies/session)
  console.log('\n[PHASE 6] Attempting in-page fetch of search API...');
  const inPageSearchEndpoints = [
    'https://blinkit.com/v6/search/listing/?search_string=milk',
    'https://api.blinkit.com/v6/search/listing/?search_string=milk',
    'https://blinkit.com/v1/layout/listing?search_string=milk',
    'https://api.blinkit.com/v1/layout/listing?search_string=milk',
  ];

  for (const ep of inPageSearchEndpoints) {
    const result = await page.evaluate(async (url) => {
      try {
        const res = await fetch(url, {
          credentials: 'include',
          headers: {
            'Accept': 'application/json, text/plain, */*',
            'app_version': '3.0',
            'web_app_version': '1000000',
            'device_id': 'web_' + Math.random().toString(36).slice(2),
          }
        });
        const text = await res.text();
        return { status: res.status, url: res.url, body: text.slice(0, 1200) };
      } catch (e) {
        return { error: e.message };
      }
    }, ep);
    console.log(`\n  In-page fetch: ${ep}`);
    console.log(`  Result: ${JSON.stringify(result).slice(0, 700)}`);
  }

  // ── PHASE 7: Capture all cookies/localStorage/sessionStorage ──────────────────
  console.log('\n[PHASE 7] Capturing session data...');
  const cookies = await page.cookies();
  saveJson('cookies.json', cookies);
  console.log(`  Cookies count: ${cookies.length}`);
  console.log(`  Cookie names: ${cookies.map(c => c.name).join(', ')}`);

  const sessionData = await page.evaluate(() => {
    const ls = {};
    for (let i = 0; i < localStorage.length; i++) {
      const k = localStorage.key(i);
      ls[k] = localStorage.getItem(k);
    }
    const ss = {};
    for (let i = 0; i < sessionStorage.length; i++) {
      const k = sessionStorage.key(i);
      ss[k] = sessionStorage.getItem(k);
    }
    return { localStorage: ls, sessionStorage: ss };
  });
  saveJson('session_data.json', sessionData);
  console.log(`  localStorage keys: ${Object.keys(sessionData.localStorage).join(', ')}`);
  console.log(`  sessionStorage keys: ${Object.keys(sessionData.sessionStorage).join(', ')}`);

  // ── PHASE 8: Try fetching search API with session cookies ──────────────────
  // Extract lat/lon from localStorage if available
  const lat = sessionData.localStorage['latitude'] || sessionData.localStorage['lat'] || '28.6139';
  const lon = sessionData.localStorage['longitude'] || sessionData.localStorage['lon'] || '77.2090';
  console.log(`\n[PHASE 8] Using coordinates: lat=${lat}, lon=${lon}`);

  const sessionEndpoints = [
    `https://blinkit.com/v6/search/listing/?search_string=milk&lat=${lat}&lon=${lon}`,
    `https://api.blinkit.com/v6/search/listing/?search_string=milk&lat=${lat}&lon=${lon}`,
    `https://blinkit.com/v1/layout/listing?search_string=milk&lat=${lat}&lon=${lon}`,
    `https://api.blinkit.com/v1/layout/listing?search_string=milk&lat=${lat}&lon=${lon}`,
  ];

  for (const ep of sessionEndpoints) {
    const result = await page.evaluate(async (url) => {
      try {
        const res = await fetch(url, {
          credentials: 'include',
          headers: {
            'Accept': 'application/json, text/plain, */*',
            'app_version': '3.0',
            'web_app_version': '1000000',
          }
        });
        const text = await res.text();
        return { status: res.status, url: res.url, body: text.slice(0, 1500) };
      } catch (e) {
        return { error: e.message };
      }
    }, ep);
    console.log(`\n  Session fetch: ${ep}`);
    console.log(`  Result: ${JSON.stringify(result).slice(0, 900)}`);

    // If we got a 200 with JSON containing product data, save it
    if (result && result.status === 200 && result.body && result.body.trim().startsWith('{')) {
      try {
        const parsed = JSON.parse(result.body);
        if (looksLikeProducts(parsed)) {
          saveJson('search_api_response.json', { url: ep, json: parsed });
          console.log('  *** FOUND WORKING SEARCH API ***');
          productJson = { url: ep, json: parsed };
        }
      } catch (_) {}
    }
  }

  // ── FINAL REPORT ──────────────────────────────
  console.log('\n' + '='.repeat(60));
  console.log('FINAL REPORT');
  console.log('='.repeat(60));

  saveJson('all_api_calls.json', requestLog);
  console.log(`\nTotal API calls intercepted: ${requestLog.length}`);

  if (productJson) {
    console.log(`\n[OK] PRODUCT API FOUND: ${productJson.url}`);
    const snippets = productJson.json && productJson.json.response && productJson.json.response.snippets
      ? productJson.json.response.snippets
      : (productJson.json && productJson.json.objects ? productJson.json.objects : []);
    console.log(`   Product count: ${snippets.length}`);
    if (snippets.length > 0) console.log(`   First item keys: ${Object.keys(snippets[0]).join(', ')}`);
  } else {
    console.log('\n[FAIL] No product API response captured. See all_api_calls.json for raw intercepts.');
  }

  if (locationJson) {
    console.log(`\n[OK] LOCATION API FOUND: ${locationJson.url}`);
  } else {
    console.log('\n[FAIL] No location API response captured.');
  }

  // Print all intercepted API URLs for reference
  console.log('\nAll intercepted API URLs:');
  requestLog.forEach(r => console.log(`  [${r.status}] ${r.url}`));

  await browser.close();
  console.log('\nDone. Output files saved to:', OUT_DIR);
}

function delay(ms) {
  return new Promise(r => setTimeout(r, ms));
}

main().catch(err => {
  console.error('Fatal error:', err);
  process.exit(1);
});
