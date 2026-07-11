/**
 * searchHelpers.js  –  Zepto scraper (fixed 2026-07-11)
 *
 * Real endpoints discovered by network intercept:
 *
 *  Search page  : https://www.zepto.com/search?query=<term>   (200 OK)
 *  Broken URL   : https://www.zepto.com/srp?q=<term>          (404)
 *
 *  Search API   : POST https://bff-gateway.zepto.com/user-search-service/api/v3/search
 *    Response structure:
 *      body.layout[]                              – widgets array
 *        .data.resolver.data.items[]              – product rows per widget
 *          .productResponse
 *            .id                                  – product ID (UUID)
 *            .product.name                        – product name
 *            .product.brand                       – brand name
 *            .productVariant.formattedPacksize     – quantity / pack size
 *            .productVariant.id                   – variant ID
 *            .productVariant.images[0].path        – image path (append to CDN base)
 *            .pricingData.mrp                     – original price in paise
 *            .pricingData.discountedSellingPrice   – final price in paise
 *            .pricingData.discount                 – discount % (integer)
 *            .outOfStock                           – boolean
 *
 *  CDN base for images:  https://cdn.zeptonow.com/production/
 *
 *  HTML fallback uses links with href containing /pn/ which ARE present
 *  in the rendered page (30+ found in test), so the HTML extractor is
 *  updated to target <a href="/pn/..."> cards.
 */

const CDN_BASE = 'https://cdn.zeptonow.com/production/';

/* ─────────────────────────────────────────────── navigateToSearch ── */

async function navigateToSearch(page, term) {
  console.log(`[Zepto] navigateToSearch: "${term}"`);

  const encTerm = encodeURIComponent(term);
  // Correct search URL – confirmed working (200)
  const searchUrl = `https://www.zepto.com/search?query=${encTerm}`;

  try {
    console.log(`[Zepto] Navigating to: ${searchUrl}`);
    await page.goto(searchUrl, {
      waitUntil: 'domcontentloaded',
      timeout: 60000
    });

    const finalUrl = page.url();
    console.log(`[Zepto] Landed at: ${finalUrl}`);

    // Short wait for XHR to fire
    await new Promise(r => setTimeout(r, 3000));
    return true;
  } catch (err) {
    console.log(`[Zepto] Error navigating to search URL: ${err.message}`);
    return false;
  }
}

/* ─────────────────────────────────────────────── hasProductCards ─── */

async function hasProductCards(page) {
  try {
    const count = await page.evaluate(() => {
      // Products render as <a href="/pn/..."> anchor cards
      return document.querySelectorAll('a[href*="/pn/"]').length;
    });
    return count > 0;
  } catch (err) {
    console.log(`[Zepto] hasProductCards error: ${err.message}`);
    return false;
  }
}

/* ────────────────────────────────────────────── ensureContentLoaded  */

async function ensureContentLoaded(page) {
  console.log('[Zepto] Ensuring content is loaded …');

  try {
    // Wait for product link cards (href="/pn/…") to appear in DOM
    await page.waitForFunction(
      () => document.querySelectorAll('a[href*="/pn/"]').length > 0,
      { timeout: 15000 }
    ).catch(e => console.log(`[Zepto] waitForFunction: ${e.message}`));

    const count = await page.evaluate(
      () => document.querySelectorAll('a[href*="/pn/"]').length
    );
    console.log(`[Zepto] Found ${count} product links on page`);

    if (count > 0) {
      await new Promise(r => setTimeout(r, 1500));
      return true;
    }

    // Check for explicit no-results message
    const noResults = await page.evaluate(() => {
      const txt = document.body.innerText;
      return (
        txt.includes('No results found') ||
        txt.includes('No products found') ||
        txt.includes("couldn't find")
      );
    });

    if (noResults) {
      console.log('[Zepto] No-results message detected');
      return false;
    }

    return false;
  } catch (err) {
    console.log(`[Zepto] ensureContentLoaded error: ${err.message}`);
    return false;
  }
}

/* ─────────────────────────────────────────────── extractProductInformation */

/**
 * Primary extractor: walks the JSON response from
 * POST /user-search-service/api/v3/search
 *
 * The response has:
 *   body.layout[].data.resolver.data.items[].productResponse
 *
 * Falls back to HTML extraction if JSON path yields nothing.
 */
function extractProductInformation(prodJson) {
  console.log('[Zepto] extractProductInformation …');

  try {
    // ── JSON path: layout-based response ──────────────────────────────
    if (prodJson && prodJson.layout && Array.isArray(prodJson.layout)) {
      const products = [];
      const seen = new Set();

      for (const widget of prodJson.layout) {
        const items =
          widget &&
          widget.data &&
          widget.data.resolver &&
          widget.data.resolver.data &&
          Array.isArray(widget.data.resolver.data.items)
            ? widget.data.resolver.data.items
            : [];

        for (const item of items) {
          const pr = item && item.productResponse;
          if (!pr) continue;

          const id = pr.id || pr.objectId;
          if (!id || seen.has(id)) continue;
          seen.add(id);

          try {
            const product    = pr.product          || {};
            const variant    = pr.productVariant   || {};
            const pricing    = pr.pricingData       || {};
            const rating     = pr.productRating     || {};

            // Prices come in paise → convert to rupees
            const mrpPaise   = pricing.mrp                     || 0;
            const salePaise  = pricing.discountedSellingPrice   || mrpPaise;
            const mrpRs      = (mrpPaise  / 100).toFixed(2);
            const saleRs     = (salePaise / 100).toFixed(2);

            const imagePath  = (variant.images && variant.images[0] && variant.images[0].path)
              ? variant.images[0].path
              : '';
            const imageUrl   = imagePath ? CDN_BASE + imagePath : '';

            const discountPct =
              pricing.discount != null
                ? pricing.discount
                : (mrpPaise && salePaise && mrpPaise > salePaise)
                ? Math.round(((mrpPaise - salePaise) / mrpPaise) * 100)
                : null;

            const savings =
              mrpPaise > salePaise
                ? `₹${((mrpPaise - salePaise) / 100).toFixed(2)}`
                : null;

            products.push({
              id,
              name          : product.name || 'Unknown Product',
              brand         : product.brand || null,
              price         : `₹${saleRs}`,
              originalPrice : mrpPaise > salePaise ? `₹${mrpRs}` : null,
              savings,
              discount      : discountPct ? `${discountPct}% OFF` : null,
              quantity      : variant.formattedPacksize || '1 item',
              deliveryTime  : '10 mins',
              imageUrl,
              available     : !pr.outOfStock,
              rating        : rating.rating || null,
              ratingCount   : rating.count || null,
              source        : 'zepto',
            });
          } catch (err) {
            console.error('[Zepto] Error processing individual product:', err.message);
          }
        }
      }

      if (products.length > 0) {
        console.log(`[Zepto] Extracted ${products.length} products from JSON layout`);
        return products;
      }
    }

    // ── Fallback: older snippets-based API format ─────────────────────
    if (prodJson && prodJson.response && prodJson.response.snippets) {
      console.log('[Zepto] Trying legacy snippets format …');
      const products = [];
      const snippets = prodJson.response.snippets.filter(
        s => s.data && s.data.name
      );

      for (const snip of snippets) {
        const data = snip.data;
        const mrp   = parseFloat(data.price || 0);
        const sale  = parseFloat(data.final_price || mrp);
        products.push({
          id            : data.identity && data.identity.id ? data.identity.id : `zepto_${Date.now()}`,
          name          : data.name || 'Unknown Product',
          price         : `₹${sale.toFixed(2)}`,
          originalPrice : mrp > sale ? `₹${mrp.toFixed(2)}` : null,
          savings       : mrp > sale ? `₹${(mrp - sale).toFixed(2)}` : null,
          discount      : (mrp > sale)
            ? `${Math.round(((mrp - sale) / mrp) * 100)}% OFF`
            : null,
          quantity      : data.weight || data.quantity || '1 item',
          deliveryTime  : data.delivery_time || '10 mins',
          imageUrl      : data.image_url || data.img_url || '',
          available     : !data.out_of_stock,
          source        : 'zepto',
        });
      }

      if (products.length > 0) {
        console.log(`[Zepto] Extracted ${products.length} products from legacy snippets`);
        return products;
      }
    }

    // ── Fallback: HTML ───────────────────────────────────────────────
    if (prodJson && prodJson.page) {
      console.log('[Zepto] Falling back to HTML extraction …');
      return extractProductsFromHTML(prodJson.page);
    }

    return [];
  } catch (err) {
    console.error('[Zepto] extractProductInformation error:', err);
    if (prodJson && prodJson.page) return extractProductsFromHTML(prodJson.page);
    return [];
  }
}

/* ──────────────────────────────────────────── extractProductsFromHTML */

async function extractProductsFromHTML(page) {
  console.log('[Zepto] HTML extraction …');

  try {
    const products = await page.evaluate((cdnBase) => {
      // Products are rendered as <a href="/pn/slug/variantId"> cards
      const cards = Array.from(document.querySelectorAll('a[href*="/pn/"]'));

      return cards.map(card => {
        try {
          const href = card.getAttribute('href') || '';
          const parts = href.split('/');
          const id = parts[parts.length - 1] || `zepto_html_${Date.now()}`;

          // Name: first sizeable text node that is NOT a price / number
          const allText = Array.from(card.querySelectorAll('*'))
            .map(el => el.childNodes)
            .reduce((acc, nl) => {
              nl.forEach(n => { if (n.nodeType === 3) acc.push(n.textContent.trim()); });
              return acc;
            }, [])
            .filter(t => t.length > 3 && !/^[₹\d]/.test(t));
          const name = allText[0] || 'Unknown Product';

          // Prices – look for ₹ text nodes
          const priceNodes = Array.from(card.querySelectorAll('*'))
            .map(el => el.textContent.trim())
            .filter(t => t.startsWith('₹') && /₹[\d,]+/.test(t));
          const price         = priceNodes[0] || 'Price unavailable';
          const originalPrice = priceNodes[1] || null;

          // Quantity
          const qtyEl = card.querySelector('[class*="packsize"], [class*="Packsize"], [class*="weight"], [class*="Weight"]');
          const quantity = qtyEl ? qtyEl.textContent.trim() : '1 item';

          // Image
          const imgEl = card.querySelector('img');
          let imageUrl = '';
          if (imgEl) {
            imageUrl = imgEl.getAttribute('src') || imgEl.getAttribute('data-src') || '';
            // Convert relative path to CDN URL if needed
            if (imageUrl && !imageUrl.startsWith('http')) {
              imageUrl = cdnBase + imageUrl.replace(/^\//, '');
            }
          }

          // Out of stock
          const cardText = card.innerText || card.textContent || '';
          const available = !cardText.toLowerCase().includes('notify') &&
                            !cardText.toLowerCase().includes('out of stock');

          return { id, name, price, originalPrice, quantity, imageUrl, available, source: 'zepto' };
        } catch (e) {
          return null;
        }
      }).filter(p => p !== null && p.name !== 'Unknown Product');
    }, CDN_BASE);

    console.log(`[Zepto] HTML extraction: ${products.length} products`);
    return products;
  } catch (err) {
    console.error('[Zepto] HTML extraction error:', err);
    return [];
  }
}

module.exports = {
  navigateToSearch,
  hasProductCards,
  ensureContentLoaded,
  extractProductInformation,
  extractProductsFromHTML,
};
