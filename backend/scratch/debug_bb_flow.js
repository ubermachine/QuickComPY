const puppeteer = require('puppeteer-extra');
const StealthPlugin = require('puppeteer-extra-plugin-stealth');
puppeteer.use(StealthPlugin());
const stealthUtils = require('../stealthUtils');
const path = require('path');

async function test() {
  console.log('Launching browser...');
  const browser = await puppeteer.launch({
    headless: "new",
    args: stealthUtils.LAUNCH_ARGS,
  });
  const page = await browser.newPage();
  await stealthUtils.applyPageStealthInjections(page);
  await page.setViewport({ width: 1280, height: 800 });

  console.log('Navigating to Bigbasket...');
  await page.goto('https://www.bigbasket.com/', { waitUntil: 'domcontentloaded', timeout: 30000 });
  await new Promise(r => setTimeout(r, 3000));

  await page.screenshot({ path: 'bb_01_initial.png' });
  console.log('Screenshot 1: initial page saved');

  // Find location button coords
  const btnInfo = await page.evaluate(() => {
    const buttons = Array.from(document.querySelectorAll('button'));
    const target = buttons.find(b => b.textContent && (
      b.textContent.includes('Deliver to') || b.textContent.includes('Delivery in') ||
      b.textContent.includes('Get it in') || b.textContent.includes('Select Location')
    ));
    if (!target) return null;
    const rect = target.getBoundingClientRect();
    return { 
      text: target.textContent.trim().slice(0, 60),
      x: rect.left + rect.width / 2, y: rect.top + rect.height / 2,
      visible: rect.width > 0 && rect.height > 0,
      inViewport: rect.top >= 0 && rect.bottom <= window.innerHeight
    };
  });
  console.log('Button info:', JSON.stringify(btnInfo));

  if (btnInfo) {
    // Scroll to button if not in viewport
    await page.evaluate(() => {
      const buttons = Array.from(document.querySelectorAll('button'));
      const target = buttons.find(b => b.textContent && (
        b.textContent.includes('Deliver to') || b.textContent.includes('Delivery in') ||
        b.textContent.includes('Get it in') || b.textContent.includes('Select Location')
      ));
      if (target) target.scrollIntoView({ block: 'center' });
    });
    await new Promise(r => setTimeout(r, 500));
    await page.mouse.click(btnInfo.x, btnInfo.y);
    console.log('Clicked location button at', btnInfo.x, btnInfo.y);
  }

  await new Promise(r => setTimeout(r, 2000));
  await page.screenshot({ path: 'bb_02_after_click.png' });
  console.log('Screenshot 2: after button click saved');

  // Check if popup input appeared
  const inputInfo = await page.evaluate(() => {
    const input = document.querySelector('input[placeholder="Search for area or street name"]');
    if (!input) return null;
    const rect = input.getBoundingClientRect();
    return { visible: rect.width > 0 && rect.height > 0, x: rect.left + rect.width/2, y: rect.top + rect.height/2 };
  });
  console.log('Input info:', JSON.stringify(inputInfo));

  if (inputInfo && inputInfo.visible) {
    await page.mouse.click(inputInfo.x, inputInfo.y);
    await page.keyboard.type('201306', { delay: 50 });
    console.log('Typed 201306');
    await new Promise(r => setTimeout(r, 3000));
    await page.screenshot({ path: 'bb_03_after_type.png' });
    console.log('Screenshot 3: after typing saved');
  }

  await browser.close();
}

test().catch(console.error);
