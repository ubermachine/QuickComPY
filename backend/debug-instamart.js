const puppeteer = require('puppeteer-extra');
const StealthPlugin = require('puppeteer-extra-plugin-stealth');
puppeteer.use(StealthPlugin());
const fs = require('fs');
const { setInstamartLocation } = require('./instamart/set-location');

async function dumpInstamart() {
  console.log('Launching browser...');
  const browser = await puppeteer.launch({ headless: "new" });
  const page = await browser.newPage();
  
  await setInstamartLocation(page, "Delhi");

  await page.goto("https://www.instamart.in/search?custom_back=true&query=milk", {
    waitUntil: 'domcontentloaded',
    timeout: 60000
  });

  await new Promise(r => setTimeout(r, 10000));
  
  const html = await page.content();
  fs.writeFileSync('instamart_search.html', html);
  console.log('Saved instamart_search.html');
  
  await browser.close();
}

dumpInstamart().catch(console.error);
