/**
 * test-extract-local.js
 * Tests product extraction logic against the saved instamart_search.html
 * without needing a live browser connection.
 */
const puppeteer = require('puppeteer-extra');
const StealthPlugin = require('puppeteer-extra-plugin-stealth');
puppeteer.use(StealthPlugin());
const fs = require('fs');
const path = require('path');
const { extractProductsFromHTML } = require('./instamart/searchHelpers');

async function testExtract() {
  console.log('=== Testing product extraction on saved HTML ===\n');

  const htmlPath = path.join(__dirname, 'instamart_search.html');
  const html = fs.readFileSync(htmlPath, 'utf8');

  const browser = await puppeteer.launch({
    headless: 'new',
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });
  const page = await browser.newPage();

  // Load the saved HTML into the page
  await page.setContent(html, { timeout: 30000 });
  await new Promise(r => setTimeout(r, 2000));

  console.log('HTML loaded. Extracting products...\n');
  const products = await extractProductsFromHTML(page);

  console.log(`\n=== RESULTS ===`);
  console.log(`Total products extracted: ${products.length}`);
  if (products.length > 0) {
    console.log('\nFirst 3 products:');
    products.slice(0, 3).forEach((p, i) => {
      console.log(`\n[${i+1}] ${p.name}`);
      console.log(`   Price:        ${p.price}`);
      console.log(`   MRP:          ${p.originalPrice || 'N/A'}`);
      console.log(`   Savings:      ${p.savings || 'N/A'}`);
      console.log(`   Quantity:     ${p.quantity}`);
      console.log(`   Discount:     ${p.discount || 'N/A'}`);
      console.log(`   DeliveryTime: ${p.deliveryTime}`);
      console.log(`   Image:        ${p.imageUrl ? p.imageUrl.substring(0,60)+'...' : 'N/A'}`);
      console.log(`   Available:    ${p.available}`);
    });
    console.log('\n=== TEST PASSED ===');
  } else {
    console.log('\n=== TEST FAILED - 0 products extracted ===');
    // Debug: dump testids
    const testids = await page.evaluate(() => {
      const map = {};
      document.querySelectorAll('[data-testid]').forEach(el => {
        const t = el.getAttribute('data-testid');
        map[t] = (map[t]||0)+1;
      });
      return map;
    });
    console.log('Available data-testid values:', JSON.stringify(testids, null, 2));
  }

  await browser.close();
}

testExtract().catch(err => { console.error('Error:', err); process.exit(1); });
