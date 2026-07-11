const puppeteer = require('puppeteer-extra');
const StealthPlugin = require('puppeteer-extra-plugin-stealth');
puppeteer.use(StealthPlugin());
const fs = require('fs');

async function dumpZepto() {
  console.log('Launching browser...');
  const browser = await puppeteer.launch({ headless: "new" });
  const page = await browser.newPage();
  
  await page.goto("https://www.zepto.com/search?query=milk", {
    waitUntil: 'domcontentloaded',
    timeout: 60000
  });

  await new Promise(r => setTimeout(r, 10000));
  
  const html = await page.content();
  fs.writeFileSync('zepto_search.html', html);
  console.log('Saved zepto_search.html');
  
  await browser.close();
}

dumpZepto().catch(console.error);
