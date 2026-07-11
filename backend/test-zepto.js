const puppeteer = require('puppeteer-extra');
const StealthPlugin = require('puppeteer-extra-plugin-stealth');
puppeteer.use(StealthPlugin());
const { setZeptoLocation } = require('./zepto/set-location');
const { navigateToSearch, ensureContentLoaded, extractProductInformation } = require('./zepto/searchHelpers');

const stealthUtils = require('./stealthUtils');

async function testZepto() {
  console.log('Launching browser...');
  const browser = await puppeteer.launch({
    headless: "new",
    args: stealthUtils.LAUNCH_ARGS,
  });
  const page = await browser.newPage();
  await stealthUtils.applyPageStealthInjections(page);
  
  let productJson = null;
  page.on('response', async (response) => {
    const url = response.url();
    if (url.includes('search') || url.includes('query')) {
      if (response.request().resourceType() === "xhr" || response.request().resourceType() === "fetch") {
        try {
          const json = await response.json();
          if (json && json.storeProducts) {
            console.log(`Intercepted product JSON from: ${url}`);
            productJson = json;
          }
        } catch (e) {}
      }
    }
  });

  console.log('Testing Zepto setLocation...');
  const locSet = await setZeptoLocation(page, "Mumbai");
  console.log('Location set:', locSet);
  
  console.log('Testing Zepto search...');
  await navigateToSearch(page, "milk");
  await ensureContentLoaded(page);

  // We should try a different search endpoint if the UI navigation failed
  const currentUrl = page.url();
  console.log('Current URL after navigation:', currentUrl);
  
  // Dump some html to see what's on the page
  const html = await page.content();
  console.log('Page has "404":', html.includes('404') || html.includes('Page Not Found'));

  await browser.close();
}

testZepto().catch(console.error);
