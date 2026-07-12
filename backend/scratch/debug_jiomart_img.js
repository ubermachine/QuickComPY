const puppeteer = require('puppeteer-extra');
const StealthPlugin = require('puppeteer-extra-plugin-stealth');
puppeteer.use(StealthPlugin());
const stealthUtils = require('../stealthUtils');

async function test() {
  const browser = await puppeteer.launch({ headless: "new", args: stealthUtils.LAUNCH_ARGS });
  const page = await browser.newPage();
  await stealthUtils.applyPageStealthInjections(page);
  
  await page.goto('https://www.jiomart.com/products?q=milk', { waitUntil: 'domcontentloaded', timeout: 30000 });
  await new Promise(r => setTimeout(r, 4000));
  
  const structure = await page.evaluate(() => {
    // Print first 50 tag names and class names
    return Array.from(document.querySelectorAll('*'))
      .slice(0, 150)
      .map(el => ({ tag: el.tagName, class: el.className, id: el.id }));
  });
  
  console.log('DOM Structure preview:', JSON.stringify(structure, null, 2));
  await browser.close();
}

test().catch(console.error);
