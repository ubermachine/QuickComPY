/**
 * check-zepto-suggestions.js
 * Opens Zepto, clicks location button, types a city, then
 * dumps all DOM elements that appear in the suggestion dropdown.
 */
const puppeteer = require('puppeteer-extra');
const StealthPlugin = require('puppeteer-extra-plugin-stealth');
puppeteer.use(StealthPlugin());

async function run() {
  const browser = await puppeteer.launch({ headless: 'new', args: ['--no-sandbox'] });
  const page = await browser.newPage();
  await page.setUserAgent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36');

  await page.goto('https://www.zepto.com/', { waitUntil: 'domcontentloaded', timeout: 60000 });
  await new Promise(r => setTimeout(r, 4000));

  // Click location button
  await page.waitForSelector('[data-testid="user-address"]', { timeout: 20000 });
  await page.click('[data-testid="user-address"]');
  await new Promise(r => setTimeout(r, 2000));

  // Capture HTML of whatever modal/overlay appeared
  const beforeType = await page.evaluate(function() {
    return {
      modal: document.querySelector('[role="dialog"]') ? document.querySelector('[role="dialog"]').innerHTML.substring(0, 2000) : null,
      inputs: Array.from(document.querySelectorAll('input')).map(function(i) { return { placeholder: i.placeholder, type: i.type, id: i.id }; }),
      testids: Array.from(document.querySelectorAll('[data-testid]')).map(function(e) { return e.getAttribute('data-testid'); })
    };
  });
  console.log('After clicking location button:');
  console.log(JSON.stringify(beforeType, null, 2));

  // Type in search input
  const inputSel = '[placeholder="Search a new address"]';
  try {
    await page.waitForSelector(inputSel, { timeout: 10000 });
    await page.click(inputSel);
    await page.type(inputSel, 'Mumbai', { delay: 80 });
    console.log('\nTyped "Mumbai", waiting for suggestions...');
    await new Promise(r => setTimeout(r, 4000));  // wait longer
  } catch(e) {
    console.log('Input not found:', e.message);
    // Try other inputs
    await page.evaluate(function() {
      var inputs = document.querySelectorAll('input');
      return Array.from(inputs).map(function(i) { return i.placeholder; });
    }).then(function(r) { console.log('Available inputs:', r); });
  }

  // Dump everything in the DOM after typing
  const afterType = await page.evaluate(function() {
    var result = {};

    // Capture suggestion list items
    var listItems = Array.from(document.querySelectorAll('li, [role="option"], [role="listitem"]'));
    result.listItems = listItems.slice(0, 10).map(function(el) {
      return {
        tag: el.tagName,
        role: el.getAttribute('role'),
        class: el.className.substring(0, 100),
        text: el.textContent.trim().substring(0, 80),
        testid: el.getAttribute('data-testid')
      };
    });

    // Divs that appeared
    var newDivs = Array.from(document.querySelectorAll('[class*="suggest"], [class*="Suggest"], [class*="dropdown"], [class*="Dropdown"], [class*="list"], [class*="List"]'));
    result.suggestionDivs = newDivs.slice(0, 10).map(function(el) {
      return {
        tag: el.tagName,
        class: el.className.substring(0, 100),
        text: el.textContent.trim().substring(0, 80)
      };
    });

    // All testids currently in DOM
    result.testids = Array.from(new Set(Array.from(document.querySelectorAll('[data-testid]')).map(function(e) { return e.getAttribute('data-testid'); })));

    // Body snippet
    result.bodySnippet = document.body.innerText.substring(0, 500);

    return result;
  });

  console.log('\nAfter typing "Mumbai":');
  console.log(JSON.stringify(afterType, null, 2));

  await browser.close();
}

run().catch(console.error);
