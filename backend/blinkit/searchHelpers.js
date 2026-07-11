/**
 * searchHelpers.js — Blinkit API-interception based search
 *
 * Strategy: Instead of DOM scraping (which breaks under bot detection),
 * we navigate to the search page and intercept the internal REST APIs:
 *   - GET /v1/layout/search?q=<term>&search_type=type_to_search
 *   - GET /v1/layout/search?offset=N&limit=12&q=<term>&...  (pagination)
 *
 * These APIs return the same JSON format as before (response.snippets[])
 * so extractProductInformation() is preserved.
 *
 * No DOM selectors, no screenshots.
 */

/**
 * Intercepts the Blinkit search API by:
 *   1. Attaching a response listener BEFORE navigation
 *   2. Navigating to /s/?q=<term> (triggers the API automatically)
 *   3. Waiting up to 15s for the JSON payload
 *
 * Returns: { url, json } or null
 */
async function interceptSearchApi(page, searchTerm) {
  const encoded = encodeURIComponent(searchTerm);
  console.log(`[interceptSearchApi] Setting up listener for: ${searchTerm}`);

  return new Promise(async (resolve) => {
    let resolved = false;
    const collected = []; // collect all search snippets across pages

    const handler = async (response) => {
      if (resolved) return;
      const url = response.url();
      const contentType = response.headers()['content-type'] || '';

      // Only look at the v1/layout/search endpoint
      if (!url.includes('blinkit.com/v1/layout/search')) return;
      if (!contentType.includes('application/json')) return;

      try {
        const json = await response.json();
        if (!json || !json.response || !Array.isArray(json.response.snippets)) return;

        const snippets = json.response.snippets;
        console.log(`[interceptSearchApi] Got ${snippets.length} snippets from: ${url}`);

        // Merge snippets from pagination
        snippets.forEach(s => collected.push(s));

        // We have enough data after the first page; don't wait for more
        if (!resolved) {
          resolved = true;
          page.off('response', handler);
          resolve({ url, json: { ...json, response: { ...json.response, snippets: collected } } });
        }
      } catch (_) { /* ignore parse errors */ }
    };

    page.on('response', handler);

    // Navigate to search URL
    try {
      await page.goto(`https://blinkit.com/s/?q=${encoded}`, {
        waitUntil: 'domcontentloaded',
        timeout: 30000,
      });
    } catch (err) {
      console.log(`[interceptSearchApi] goto error (may be ok): ${err.message}`);
    }

    // Allow time for the API calls to fire and be intercepted
    await delay(8000);

    if (!resolved) {
      resolved = true;
      page.off('response', handler);
      console.log('[interceptSearchApi] Timeout — no search API response intercepted');
      resolve(null);
    }
  });
}

/**
 * Full search flow: set up interceptor, navigate, return products.
 * This replaces the old navigateToSearch + ensureContentLoaded + extractProductInformation pattern.
 */
async function searchBlinkit(page, searchTerm) {
  console.log(`[searchBlinkit] Searching for: ${searchTerm}`);
  const intercepted = await interceptSearchApi(page, searchTerm);

  if (!intercepted) {
    console.error('[searchBlinkit] Failed to intercept search API');
    return [];
  }

  return extractProductInformation(intercepted.json);
}

/**
 * Legacy: Navigate to search URL.
 * Now just navigates — call interceptSearchApi or searchBlinkit for API-based results.
 */
async function navigateToSearch(page, searchTerm) {
  console.log(`[navigateToSearch] Navigating to search URL for: ${searchTerm}`);
  try {
    const encoded = encodeURIComponent(searchTerm);
    await page.goto(`https://blinkit.com/s/?q=${encoded}`, {
      waitUntil: 'domcontentloaded',
      timeout: 30000,
    });
    await delay(2000);
    return true;
  } catch (err) {
    console.log(`[navigateToSearch] Error: ${err.message}`);
    return false;
  }
}

/**
 * Legacy: Kept for backward compatibility; now a no-op since we use API interception.
 */
async function ensureContentLoaded(page) {
  await delay(3000);
  return true;
}

/**
 * Extracts standardized product objects from a Blinkit /v1/layout/search JSON response.
 *
 * Snippet types handled:
 *   - product_card_snippet_type_2  →  data.identity.id = product id (numeric string)
 *   - listing_container            →  container, skip
 *   - product_container            →  header, skip
 *
 * Product fields in snippet.data:
 *   identity.id          → product id
 *   name.text            → name
 *   normal_price.text    → selling price  (e.g. "₹52")
 *   mrp.text             → original price / MRP
 *   variant.text         → quantity/weight (e.g. "1 L")
 *   image.url            → product image
 *   eta_tag.title.text   → delivery time (e.g. "10 mins")
 *   offer_tag            → discount label
 *   is_sold_out          → availability
 *   inventory            → stock count
 */
function extractProductInformation(prodJson) {
  console.log('[extractProductInformation] Extracting products from JSON response...');
  const prods = [];

  if (!prodJson || !prodJson.response || !Array.isArray(prodJson.response.snippets)) {
    console.error('[extractProductInformation] Invalid JSON structure — expected response.snippets[]');
    return prods;
  }

  const snippets = prodJson.response.snippets;

  snippets.forEach((snip, idx) => {
    const raw = snip.data;

    // Skip containers / headers / non-product widgets
    if (
      !raw ||
      snip.widget_type === 'image_text_vr_type_header' ||
      !raw.name ||
      !raw.identity ||
      raw.identity.id === 'product_container' ||
      raw.identity.id === 'listing_container' ||
      raw.identity.id === 'recent_searches_pill_container'
    ) {
      return;
    }

    // Only process numeric product IDs (skip string container IDs)
    const idNum = parseInt(raw.identity.id, 10);
    if (isNaN(idNum)) return;

    try {
      const id = raw.identity.id;
      const name = raw.name && raw.name.text ? raw.name.text.replace(/<[^>]+>/g, '').trim() : 'N/A';

      let price = 'N/A';
      if (raw.normal_price && raw.normal_price.text) {
        price = raw.normal_price.text;
      } else if (typeof raw.price === 'number') {
        price = `₹${raw.price.toFixed(2)}`;
      }

      let origPrice = null;
      if (raw.mrp && raw.mrp.text) {
        origPrice = raw.mrp.text;
      }

      const qty = raw.variant && raw.variant.text ? raw.variant.text : 'N/A';
      const imgUrl = raw.image && raw.image.url ? raw.image.url : '';
      const delTime = raw.eta_tag && raw.eta_tag.title && raw.eta_tag.title.text
        ? raw.eta_tag.title.text
        : 'N/A';

      let disc = null;
      if (raw.offer_tag && raw.offer_tag.title && raw.offer_tag.title.text) {
        disc = raw.offer_tag.title.text.replace(/\n/g, ' ');
      }

      const avail = raw.hasOwnProperty('is_sold_out')
        ? !raw.is_sold_out
        : raw.hasOwnProperty('inventory')
          ? raw.inventory > 0
          : true;

      let savings = null;
      if (origPrice && price) {
        const prMatch = price.match(/₹\s*(\d+(?:\.\d+)?)/);
        const opMatch = origPrice.match(/₹\s*(\d+(?:\.\d+)?)/);
        if (prMatch && opMatch) {
          const cur = parseFloat(prMatch[1]);
          const orig = parseFloat(opMatch[1]);
          if (!isNaN(orig) && !isNaN(cur) && orig > cur) {
            savings = `₹${(orig - cur).toFixed(0)}`;
          }
        }
      }

      prods.push({
        id,
        name,
        price,
        originalPrice: origPrice,
        savings,
        quantity: qty,
        deliveryTime: delTime,
        discount: disc,
        imageUrl: imgUrl,
        available: avail,
      });
    } catch (err) {
      console.error(`[extractProductInformation] Error on snippet[${idx}]: ${err.message}`);
    }
  });

  console.log(`[extractProductInformation] Extracted ${prods.length} products`);
  return prods;
}

function delay(ms) {
  return new Promise(r => setTimeout(r, ms));
}

module.exports = {
  ensureContentLoaded,
  extractProductInformation,
  navigateToSearch,
  interceptSearchApi,
  searchBlinkit,
};
