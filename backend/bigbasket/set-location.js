/**
 * setBigbasketLocation - Fast location setup for Bigbasket.
 * Strategy: Skip UI entirely. Bigbasket search works with just the pincode
 * in the URL (/ps/?q=...). Return the pincode immediately.
 * UI navigation only happens as a one-time best-effort if the page is fresh.
 */

const LOCATION_TO_PINCODE = {
  'supertech eco village-1': '201306',
  'supertech eco village 1': '201306',
  'supertech ecovillage-1': '201306',
  'supertech ecovillage 1': '201306',
  '201306': '201306',
  '201318': '201318',
  'noida': '201301',
  'delhi': '110001',
  'new delhi': '110001',
  'gurgaon': '122001',
  'gurugram': '122001',
  'mumbai': '400001',
  'bengaluru': '560001',
  'bangalore': '560001',
};

function resolvePincode(loc) {
  if (!loc) return loc;
  if (/^\d{6}$/.test(loc.trim())) return loc.trim();
  return LOCATION_TO_PINCODE[loc.toLowerCase().trim()] || loc;
}

async function setBigbasketLocation(page, loc) {
  const pincode = resolvePincode(loc);
  console.log(`Setting Bigbasket location to: ${loc} (pincode: ${pincode})`);

  try {
    // Fast path: if already on bigbasket.com and location is confirmed, return it
    const currentUrl = page.url() || '';
    if (currentUrl.includes('bigbasket.com')) {
      const confirmed = await isLocSet(page);
      if (confirmed && !confirmed.includes('Select Location')) {
        console.log(`[BB] Location already confirmed: "${confirmed}"`);
        return confirmed;
      }
    }

    // If page is not on bigbasket.com at all, do a minimal navigation
    if (!currentUrl.includes('bigbasket.com')) {
      await page.goto('https://www.bigbasket.com/', {
        waitUntil: 'domcontentloaded',
        timeout: 20000
      }).catch(e => console.log(`[BB] goto warn: ${e.message}`));

      // Quick attempt to set location via UI (best effort, 15s total budget)
      await setBigbasketLocationViaUI(page, pincode).catch(() => {});
    }

    // Return pincode — Bigbasket search URL uses session context
    console.log(`[BB] Location setup done. Returning pincode: ${pincode}`);
    return pincode;

  } catch (err) {
    console.error('[BB] Error setting location:', err.message);
    return pincode; // Always return pincode, never fail
  }
}

async function setBigbasketLocationViaUI(page, pincode) {
  try {
    // Try clicking location button using real mouse coordinates
    const btnCoords = await page.evaluate(() => {
      const buttons = Array.from(document.querySelectorAll('button'));
      const target = buttons.find(b => b.textContent && (
        b.textContent.includes('Select Location') ||
        b.textContent.includes('Deliver to') ||
        b.textContent.includes('Delivery in') ||
        b.textContent.includes('Get it in')
      ));
      if (!target) return null;
      const rect = target.getBoundingClientRect();
      return { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2, text: target.textContent.trim().slice(0, 40) };
    });

    if (!btnCoords) return null;

    // If location already shows a pincode, we're done
    if (!btnCoords.text.includes('Select Location')) {
      console.log(`[BB] Location already set in button: "${btnCoords.text}"`);
      return btnCoords.text;
    }

    console.log(`[BB] Clicking location button...`);
    await page.mouse.click(btnCoords.x, btnCoords.y);

    // Wait for either popup input or page navigation
    await Promise.race([
      page.waitForSelector('input[placeholder="Search for area or street name"]', { timeout: 6000, visible: true }),
      page.waitForNavigation({ waitUntil: 'domcontentloaded', timeout: 6000 })
    ]).catch(() => {});

    const inputCoords = await page.evaluate(() => {
      const input = document.querySelector('input[placeholder="Search for area or street name"]');
      if (!input) return null;
      const rect = input.getBoundingClientRect();
      return rect.width > 0 ? { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 } : null;
    });

    if (!inputCoords) return null;

    await page.mouse.click(inputCoords.x, inputCoords.y);
    await page.keyboard.type(pincode, { delay: 50 });
    console.log(`[BB] Typed: ${pincode}`);

    // Wait for suggestions with digits (location results, not nav)
    await page.waitForFunction((pin) => {
      const input = document.querySelector('input[placeholder="Search for area or street name"]');
      if (!input) return false;
      let container = input.parentElement;
      for (let i = 0; i < 10; i++) {
        if (!container) break;
        const items = Array.from(container.querySelectorAll('li'))
          .filter(li => /\d/.test(li.textContent || ''));
        if (items.length > 0) return true;
        container = container.parentElement;
      }
      return false;
    }, { timeout: 5000 }, pincode).catch(() => {});

    const suggestion = await page.evaluate((pin) => {
      const input = document.querySelector('input[placeholder="Search for area or street name"]');
      if (!input) return null;
      let container = input.parentElement;
      for (let i = 0; i < 10; i++) {
        if (!container) break;
        const items = Array.from(container.querySelectorAll('li'))
          .filter(li => /\d/.test(li.textContent || ''));
        if (items.length > 0) {
          const target = items.find(li => (li.textContent || '').includes(pin)) || items[0];
          const rect = target.getBoundingClientRect();
          return { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2, text: target.textContent.trim().slice(0, 60) };
        }
        container = container.parentElement;
      }
      return null;
    }, pincode);

    if (!suggestion) return null;

    await page.mouse.click(suggestion.x, suggestion.y);
    console.log(`[BB] Clicked suggestion: "${suggestion.text}"`);

    await page.waitForFunction(() => {
      return Array.from(document.querySelectorAll('button')).some(b =>
        b.textContent && (b.textContent.includes('Delivery in') || b.textContent.includes('Get it in')) &&
        !b.textContent.includes('Select Location')
      );
    }, { timeout: 6000 }).catch(() => {});

    return await isLocSet(page);
  } catch (err) {
    console.log(`[BB] UI setup error: ${err.message}`);
    return null;
  }
}

async function isLocSet(page) {
  try {
    return await page.evaluate(() => {
      const button = Array.from(document.querySelectorAll('button')).find(b =>
        b.textContent && (
          b.textContent.includes('Deliver to') ||
          b.textContent.includes('Delivery in') ||
          b.textContent.includes('Get it in') ||
          b.textContent.includes('Select Location')
        )
      );
      if (button) {
        const txt = button.textContent.trim();
        if (txt.includes('Select Location')) return null;
        return txt;
      }
      return null;
    });
  } catch (e) {
    return null;
  }
}

module.exports = { setBigbasketLocation, isLocSet };
