/**
 * set-location.js  –  Zepto location setter (fixed 2026-07-11)
 *
 * Confirmed selectors (from live DOM inspection):
 *   Location button  : [data-testid="user-address"]   text: "Select Location"
 *   Search input     : [placeholder="Search a new address"]
 *   Suggestion items : Varies – try several fallbacks
 *   Confirm button   : button with text containing "Confirm"
 *
 * Domain: www.zepto.com  (NOT www.zeptonow.com – the old domain redirects)
 */

async function setZeptoLocation(page, loc) {
  console.log(`[Zepto] setZeptoLocation: "${loc}"`);
  const maxAttempts = 2;

  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    console.log(`[Zepto] Location attempt ${attempt}/${maxAttempts}`);

    try {
      // Navigate to homepage if not already there
      if (!page.url().includes('zepto.com')) {
        await page.goto('https://www.zepto.com/', {
          waitUntil: 'domcontentloaded',
          timeout: 60000
        });
        await new Promise(r => setTimeout(r, 3000));
      }

      // ── Click the location button ──────────────────────────────────
      try {
        await page.waitForSelector('[data-testid="user-address"]', { timeout: 20000 });
        await page.click('[data-testid="user-address"]');
        console.log('[Zepto] Clicked user-address button');
        await new Promise(r => setTimeout(r, 2000));
      } catch (e) {
        console.log('[Zepto] user-address selector failed, trying header button:', e.message);
        // Fallback: first header button usually is location
        await page.click('header button').catch(() => {});
        await new Promise(r => setTimeout(r, 2000));
      }

      // ── Type in the location search box ───────────────────────────
      const inputSel = '[placeholder="Search a new address"]';
      try {
        await page.waitForSelector(inputSel, { timeout: 15000 });
        await page.click(inputSel);
        await new Promise(r => setTimeout(r, 500));
        await page.type(inputSel, loc, { delay: 80 });
        console.log(`[Zepto] Typed location: "${loc}"`);
        await new Promise(r => setTimeout(r, 2500)); // wait for suggestions
      } catch (e) {
        console.log('[Zepto] Location search input not found:', e.message);
        continue; // retry
      }

      // ── Click the first suggestion ─────────────────────────────────
      const suggestionSelectors = [
        // Modern structure: list items in the suggestion dropdown
        '[class*="suggestion"]:first-child',
        '[class*="Suggestion"]:first-child',
        'ul[role="listbox"] li:first-child',
        '[role="option"]:first-child',
        '[class*="LocationSuggestion"]:first-child',
        '[class*="location-suggestion"]:first-child',
        // Generic list approach
        'ul li:first-child',
        '.flex:nth-child(1) > .ml-4 > div > .font-heading', // legacy selector kept as fallback
      ];

      let clickedSuggestion = false;
      for (const sel of suggestionSelectors) {
        try {
          const el = await page.$(sel);
          if (el) {
            await el.click();
            console.log(`[Zepto] Clicked suggestion with: ${sel}`);
            clickedSuggestion = true;
            await new Promise(r => setTimeout(r, 2000));
            break;
          }
        } catch (e) {
          // try next selector
        }
      }

      if (!clickedSuggestion) {
        console.log('[Zepto] Could not find suggestion element, pressing Enter');
        await page.keyboard.press('Enter');
        await new Promise(r => setTimeout(r, 2000));
      }

      // ── Confirm location if a confirm button appears ───────────────
      const confirmSelectors = [
        'button[class*="confirm"]',
        'button[class*="Confirm"]',
        '.bg-skin-primary > .flex',      // legacy selector
        '[class*="primary"] button',
        'button:not([disabled])',         // last resort: first enabled button
      ];

      for (const sel of confirmSelectors) {
        try {
          const confirmEl = await page.$(sel);
          if (confirmEl) {
            const txt = await page.evaluate(el => el.textContent.trim(), confirmEl);
            if (txt && (txt.toLowerCase().includes('confirm') || txt.toLowerCase().includes('continue') || txt.toLowerCase().includes('set'))) {
              await confirmEl.click();
              console.log(`[Zepto] Clicked confirm button: "${txt}"`);
              await new Promise(r => setTimeout(r, 4000));
              break;
            }
          }
        } catch (e) {
          // continue
        }
      }

      // ── Check if location was set ──────────────────────────────────
      const locTitle = await isLocSet(page);
      if (locTitle) {
        console.log(`[Zepto] Location set to: ${locTitle}`);
        return locTitle;
      }

      if (attempt < maxAttempts) {
        console.log('[Zepto] Location not confirmed, reloading and retrying …');
        await page.reload({ waitUntil: 'domcontentloaded', timeout: 60000 });
        await new Promise(r => setTimeout(r, 3000));
      }
    } catch (err) {
      console.error(`[Zepto] Error setting location (attempt ${attempt}):`, err.message);
      if (attempt >= maxAttempts) return null;
      await new Promise(r => setTimeout(r, 4000));
    }
  }

  return null;
}

/* ─────────────────────────────────────────────────────── isLocSet ── */

async function isLocSet(page) {
  console.log('[Zepto] Checking if location is set …');

  try {
    await new Promise(r => setTimeout(r, 2000));

    // Primary check: the user-address testid should no longer say "Select Location"
    const addrEl = await page.$('[data-testid="user-address"]');
    if (addrEl) {
      const txt = await page.evaluate(el => el.textContent.trim(), addrEl);
      if (txt && txt.length > 2 && !txt.toLowerCase().includes('select') && !txt.toLowerCase().includes('enter')) {
        console.log(`[Zepto] Location confirmed via user-address: "${txt}"`);
        return txt;
      }
    }

    // Fallback selectors
    const fallbackSels = [
      '[class*="location-display"]',
      '[class*="address-display"]',
      '.selected-location',
      '.delivery-location',
      '.font-medium.text-sm',
      '.font-heading',
      '[aria-label*="location"]',
      '[aria-label*="address"]',
    ];

    for (const sel of fallbackSels) {
      try {
        const el = await page.$(sel);
        if (!el) continue;
        const txt = await page.evaluate(el => el.textContent.trim(), el);
        if (txt && txt.length > 2 && !txt.toLowerCase().includes('select') && !txt.toLowerCase().includes('enter')) {
          console.log(`[Zepto] Location via fallback (${sel}): "${txt}"`);
          return txt;
        }
      } catch (e) { /* next */ }
    }

    // If we're on the main page and products/categories are visible, assume location is set
    const onMain = await page.evaluate(() => {
      return (
        window.location.pathname === '/' &&
        document.querySelectorAll('a[href*="/cn/"]').length > 0
      );
    });

    if (onMain) {
      console.log('[Zepto] On homepage with categories, assuming location is set');
      return 'Location Set';
    }

    return null;
  } catch (err) {
    console.error('[Zepto] isLocSet error:', err.message);
    return null;
  }
}

module.exports = { setZeptoLocation, isLocSet };
