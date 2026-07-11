const puppeteer = require('puppeteer-extra');
const StealthPlugin = require('puppeteer-extra-plugin-stealth');
puppeteer.use(StealthPlugin());
const { setBigbasketLocation } = require('./bigbasket/set-location');
const { navigateToSearch, ensureContentLoaded, extractProductInformation } = require('./bigbasket/searchHelpers');

async function testBigbasket() {
  console.log('Launching browser...');
  const browser = await puppeteer.launch({ headless: "new" });
  const page = await browser.newPage();
  
  let productJson = null;
  page.on('response', async (response) => {
    const url = response.url();
    if (response.request().resourceType() === "xhr" || response.request().resourceType() === "fetch") {
      try {
        const json = await response.json();
        if (json && json.tabs && Array.isArray(json.tabs) && json.tabs[0] && json.tabs[0].product_info) {
          console.log(`Intercepted Bigbasket JSON from: ${url}`);
          productJson = json;
        }
      } catch (e) {}
    }
  });

  console.log('Testing setLocation...');
  const locSet = await setBigbasketLocation(page, "Delhi");
  console.log('Location set:', locSet);
  
  console.log('Testing search...');
  await navigateToSearch(page, "milk");
  await ensureContentLoaded(page);
  
  let products = [];
  if (productJson) {
    products = extractProductInformation(productJson);
  }
  
  if (products.length === 0) {
    console.log("No products from JSON, trying HTML extraction");
    products = await extractProductInformation({ useHtmlExtraction: true, page: page });
  }

  console.log('Extracted products:', products.length);
  if (products.length > 0) {
    console.log('First product:', products[0]);
  }
  
  await browser.close();
}

testBigbasket().catch(console.error);
