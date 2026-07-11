const puppeteer = require('puppeteer-extra');
const StealthPlugin = require('puppeteer-extra-plugin-stealth');
puppeteer.use(StealthPlugin());
const { setBlinkitLocation } = require('./blinkit/set-location');
const { navigateToSearch, ensureContentLoaded, extractProductInformation } = require('./blinkit/searchHelpers');

const stealthUtils = require('./stealthUtils');

async function test() {
  console.log('Launching browser...');
  const browser = await puppeteer.launch({
    headless: "new",
    args: stealthUtils.LAUNCH_ARGS,
  });
  const page = await browser.newPage();
  await stealthUtils.applyPageStealthInjections(page);
  
  // Set up network interception for blinkit
  let productJson = null;
  page.on('response', async (response) => {
    const url = response.url();
    if (response.request().resourceType() === "xhr" || response.request().resourceType() === "fetch") {
      try {
        const json = await response.json();
        if (json && json.response && Array.isArray(json.response.snippets) && !url.includes("empty_search")) {
          console.log(`Intercepted product JSON from: ${url}`);
          productJson = json;
        }
      } catch (e) {
        // Ignore
      }
    }
  });
  
  console.log('Testing setLocation...');
  const locSet = await setBlinkitLocation(page, "Delhi");
  console.log('Location set:', locSet);
  
  console.log('Testing search...');
  await navigateToSearch(page, "milk");
  await ensureContentLoaded(page);
  
  if (productJson) {
    const products = extractProductInformation(productJson);
    console.log('Extracted products:', products.length);
    console.log('First product:', products[0]);
  } else {
    console.log('No product JSON intercepted.');
  }
  
  await browser.close();
}

test().catch(console.error);
