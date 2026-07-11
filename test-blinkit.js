const puppeteer = require('puppeteer');
const { setBlinkitLocation } = require('./backend/blinkit/set-location');
const { navigateToSearch, ensureContentLoaded } = require('./backend/blinkit/searchHelpers');

async function test() {
  console.log('Launching browser...');
  const browser = await puppeteer.launch({ headless: "new" });
  const page = await browser.newPage();
  
  // Intercept responses to test JSON extraction if needed, but the user prompt says:
  // "extracting products). Ensure the CSS selectors used for product name, price, original price, etc. match the live DOM."
  // Wait, in searchHelpers.js, `extractProductInformation` expects `prodJson`. 
  // Let's see if there are other extraction methods in other files, or if `extractProductInformation` is using DOM extraction in another file. 
  // Ah, the user mentions "Ensure the CSS selectors used for product name, price, original price, etc. match the live DOM." 
  // Let's check `backend/blinkit/search.js` maybe?
  console.log('Testing setLocation...');
  const locSet = await setBlinkitLocation(page, "Delhi");
  console.log('Location set:', locSet);
  
  console.log('Testing search...');
  await navigateToSearch(page, "milk");
  await ensureContentLoaded(page);
  
  // Let's just log the first product we can find on the page
  const html = await page.content();
  console.log('Content length:', html.length);
  
  await browser.close();
}

test().catch(console.error);
