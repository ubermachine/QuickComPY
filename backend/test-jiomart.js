const puppeteer = require('puppeteer-extra');
const StealthPlugin = require('puppeteer-extra-plugin-stealth');
puppeteer.use(StealthPlugin());
const { setJioMartLocation } = require('./jiomart/set-location');
const { navigateToSearch, ensureContentLoaded, extractProductInformation } = require('./jiomart/searchHelpers');

const stealthUtils = require('./stealthUtils');

async function testJioMart() {
  console.log('Launching browser...');
  const browser = await puppeteer.launch({
    headless: "new",
    args: stealthUtils.LAUNCH_ARGS,
  });
  const page = await browser.newPage();
  await stealthUtils.applyPageStealthInjections(page);

  console.log('Testing JioMart setLocation...');
  const locSet = await setJioMartLocation(page, "Mumbai");
  console.log('Location set:', locSet);

  console.log('Testing JioMart search...');
  await navigateToSearch(page, "milk");
  const contentLoaded = await ensureContentLoaded(page);
  console.log('Content loaded:', contentLoaded);

  const products = await extractProductInformation({ page: page });
  console.log('Extracted products count:', products.length);
  if (products.length > 0) {
    console.log('First product:', products[0]);
  }

  await browser.close();
}

testJioMart().catch(console.error);
