const puppeteer = require('puppeteer-extra');
const StealthPlugin = require('puppeteer-extra-plugin-stealth');
puppeteer.use(StealthPlugin());
const { setInstamartLocation } = require('./instamart/set-location');
const { navigateToSearch, ensureContentLoaded, extractProductInformation } = require('./instamart/searchHelpers');

async function testInstamart() {
  console.log('Launching browser...');
  const browser = await puppeteer.launch({ headless: "new" });
  const page = await browser.newPage();
  
  let productJson = null;
  page.on('response', async (response) => {
    const url = response.url();
    if (url.includes('search')) {
      if (response.request().resourceType() === "xhr" || response.request().resourceType() === "fetch") {
        try {
          const json = await response.json();
          // Instamart might have different JSON format, let's catch it if it exists
          if (json && json.data) {
            console.log(`Intercepted product JSON from: ${url}`);
            productJson = json;
          }
        } catch (e) {}
      }
    }
  });

  console.log('Testing setLocation...');
  const locSet = await setInstamartLocation(page, "Delhi");
  console.log('Location set:', locSet);
  
  console.log('Testing search...');
  await navigateToSearch(page, "milk");
  await ensureContentLoaded(page);
  
  let products = [];
  if (productJson) {
    products = extractProductInformation({ response: productJson }); // adjust if needed
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

testInstamart().catch(console.error);
