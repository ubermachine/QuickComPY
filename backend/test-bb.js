const puppeteer = require('puppeteer-extra');
const StealthPlugin = require('puppeteer-extra-plugin-stealth');
puppeteer.use(StealthPlugin());

const { setBigbasketLocation } = require('./bigbasket/set-location.js');
const { navigateToSearch, ensureContentLoaded, extractProductInformation } = require('./bigbasket/searchHelpers.js');

async function testBB() {
  console.log("Launching browser...");
  const browser = await puppeteer.launch({ headless: 'new', args: ['--no-sandbox'] });
  const page = await browser.newPage();
  
  // Set user agent
  await page.setUserAgent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36');
  
  console.log("Testing setLocation...");
  const locResult = await setBigbasketLocation(page, "Delhi");
  console.log("Location result:", locResult);

  console.log("Testing search for 'milk'...");
  await navigateToSearch(page, "milk");
  await ensureContentLoaded(page);
  
  const products = await extractProductInformation({ page, useHtmlExtraction: true });
  console.log(`Found ${products.length} products`);
  console.log(JSON.stringify(products.slice(0, 3), null, 2));

  await browser.close();
}

testBB().catch(console.error);
