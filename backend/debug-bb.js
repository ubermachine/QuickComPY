const puppeteer = require('puppeteer-extra');
const StealthPlugin = require('puppeteer-extra-plugin-stealth');
puppeteer.use(StealthPlugin());
const fs = require('fs');

async function debugBB() {
  console.log("Launching browser...");
  const browser = await puppeteer.launch({ headless: 'new', args: ['--no-sandbox'] });
  const page = await browser.newPage();
  await page.setViewport({ width: 1280, height: 800 });
  await page.setUserAgent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36');
  
  console.log("Going to BigBasket...");
  await page.goto("https://www.bigbasket.com/", { waitUntil: 'networkidle2', timeout: 60000 });
  
  await page.screenshot({ path: 'bb_home.png' });
  const homeHtml = await page.content();
  fs.writeFileSync('bb_home.html', homeHtml);
  console.log("Saved bb_home.png and bb_home.html");

  console.log("Searching for milk...");
  await page.goto("https://www.bigbasket.com/ps/?q=milk", { waitUntil: 'networkidle2', timeout: 60000 });
  await page.screenshot({ path: 'bb_search.png' });
  const searchHtml = await page.content();
  fs.writeFileSync('bb_search.html', searchHtml);
  console.log("Saved bb_search.png and bb_search.html");

  await browser.close();
}

debugBB().catch(console.error);
