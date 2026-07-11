const puppeteer = require('puppeteer');

async function debugBlinkit() {
  console.log('Launching browser...');
  const browser = await puppeteer.launch({ headless: "new" });
  const page = await browser.newPage();
  
  await page.setViewport({ width: 1280, height: 800 });
  
  console.log('Going to blinkit...');
  await page.goto("https://blinkit.com/", {
    waitUntil: "domcontentloaded",
    timeout: 300000,
  });
  
  await new Promise(r => setTimeout(r, 5000));
  
  await page.screenshot({ path: 'blinkit_home.png' });
  console.log('Saved blinkit_home.png');
  
  const html = await page.content();
  const fs = require('fs');
  fs.writeFileSync('blinkit_home.html', html);
  
  await browser.close();
}

debugBlinkit().catch(console.error);
