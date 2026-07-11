/**
 * searchHelpers.js - JioMart search helpers
 */

async function navigateToSearch(page, searchTerm) {
  try {
    const encSearchTerm = encodeURIComponent(searchTerm);
    console.log(`[JioMart] Navigating directly to: https://www.jiomart.com/products?q=${encSearchTerm}`);
    await page.goto(`https://www.jiomart.com/products?q=${encSearchTerm}`, {
      waitUntil: 'domcontentloaded',
      timeout: 45000
    });
    return true;
  } catch (err) {
    console.error(`[JioMart] Navigation error: ${err.message}`);
    return false;
  }
}

async function ensureContentLoaded(page) {
  try {
    // Wait for the productCard container or page search list to render
    await page.waitForSelector('.productCard__cardWrapper', { timeout: 15000 });
    console.log('[JioMart] Content loaded successfully');
    return true;
  } catch (err) {
    console.warn(`[JioMart] Content loading warning or timeout: ${err.message}`);
    return false;
  }
}

async function extractProductInformation(pageOrJson) {
  console.log('[JioMart] Extraction started...');
  const page = pageOrJson.page;
  if (!page) {
    console.error('[JioMart] No page object found for extraction');
    return [];
  }

  try {
    const products = await page.evaluate(() => {
      const items = [];
      const cards = document.querySelectorAll('.productCard__cardWrapper');
      cards.forEach((card, idx) => {
        const nameEl = card.querySelector('.productCard__productTitle');
        const priceEl = card.querySelector('.PriceContainer__currentPrice');
        const mrpEl = card.querySelector('.PriceContainer__originalPrice');
        const qtyEl = card.querySelector('.productCard__sizeSpan') || card.querySelector('.productCard__quantitySelector');
        const imgEl = card.querySelector('.productCard__productImage');

        if (nameEl && priceEl) {
          const price = priceEl.innerText.trim();
          const originalPrice = mrpEl ? mrpEl.innerText.trim() : null;

          let savings = null;
          let discount = null;
          if (price && originalPrice) {
            const spVal = parseFloat(price.replace(/[^\d.]/g, ''));
            const mrpVal = parseFloat(originalPrice.replace(/[^\d.]/g, ''));
            if (!isNaN(spVal) && !isNaN(mrpVal) && mrpVal > spVal) {
              savings = `₹${(mrpVal - spVal).toFixed(2)}`;
              discount = `${Math.round(((mrpVal - spVal) / mrpVal) * 100)}% OFF`;
            }
          }

          items.push({
            id: `jm_${idx}`,
            name: nameEl.innerText.trim(),
            price,
            originalPrice,
            savings,
            discount,
            quantity: qtyEl ? qtyEl.innerText.trim() : '',
            deliveryTime: 'Standard Delivery',
            imageUrl: imgEl ? imgEl.src || imgEl.getAttribute('data-src') || imgEl.getAttribute('src') || '' : '',
            available: true,
            source: 'jiomart'
          });
        }
      });
      return items;
    });

    console.log(`[JioMart] Extracted ${products.length} products`);
    return products;
  } catch (err) {
    console.error(`[JioMart] Error during extraction: ${err.message}`);
    return [];
  }
}

module.exports = {
  navigateToSearch,
  ensureContentLoaded,
  extractProductInformation
};
