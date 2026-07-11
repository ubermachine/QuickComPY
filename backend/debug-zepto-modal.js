const puppeteer = require('puppeteer-extra');
const StealthPlugin = require('puppeteer-extra-plugin-stealth');
puppeteer.use(StealthPlugin());

async function main() {
  console.log("Launching browser for Zepto address modal inspection...");
  const browser = await puppeteer.launch({
    headless: 'new',
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });
  const page = await browser.newPage();
  await page.setViewport({ width: 1366, height: 768 });
  await page.setUserAgent(
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
  );

  console.log("Navigating to Zepto...");
  await page.goto('https://www.zepto.com/', { waitUntil: 'domcontentloaded', timeout: 60000 });
  await new Promise(r => setTimeout(r, 4000));

  console.log("Clicking user-address button...");
  await page.click('[data-testid="user-address"]');
  await new Promise(r => setTimeout(r, 2000));

  console.log("Typing 'Mumbai' in the input box...");
  const inputSel = '[placeholder="Search a new address"]';
  await page.type(inputSel, 'Mumbai', { delay: 100 });
  
  console.log("Waiting for suggestion item...");
  await page.waitForSelector('[data-testid="address-search-item"]', { timeout: 10000 });
  
  console.log("Clicking the first suggestion...");
  await page.click('[data-testid="address-search-item"]');
  
  console.log("Waiting 3 seconds for confirm screen/modal...");
  await new Promise(r => setTimeout(r, 3000));

  console.log("Checking page URL:", page.url());

  console.log("Dumping all button texts on confirm screen:");
  const buttonsInfo = await page.evaluate(() => {
    const btns = Array.from(document.querySelectorAll('button'));
    return btns.map(b => ({
      text: b.textContent.trim(),
      class: b.className,
      testid: b.getAttribute('data-testid') || ''
    }));
  });
  console.log(JSON.stringify(buttonsInfo, null, 2));

  console.log("Dumping all text on page to find any confirm text:");
  const pageText = await page.evaluate(() => document.body.innerText.slice(0, 1000));
  console.log(pageText);

  await browser.close();
}

main().catch(console.error);
