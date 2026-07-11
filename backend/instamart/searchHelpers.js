/**
 * searchHelpers.js - Fixed for Swiggy Instamart (swiggy.com/instamart)
 *
 * Selector analysis from live HTML snapshot (instamart_search.html):
 *   Product card:   data-testid="item-collection-card-full"  (32 cards found)
 *   Product name:   ._1lbNR  (class also includes iPErou)
 *   Current price:  ._2jn41  (class also includes iQcBUp) - number only, ? via CSS ::before
 *   Original price: ._3eAjW._2jn41._1VrXB  (strikethrough MRP) - empty when no discount
 *   Quantity/weight:._3wq_F  (class also includes bCqPoH)
 *   Description:    ._3bM-V  (class also includes diZRny)
 *   Discount text:  data-testid="offer-text"
 *   Image:          img._16I1D  (or img[alt])
 *   Delivery time:  [aria-label*="Delivery in"] -> text contains "7 MINS" etc.
 *   Search bar:     data-testid="search-page-header-search-bar-input"
 */

async function navigateToSearch(page, searchTerm) {
  console.log(`Navigating to Instamart search for: ${searchTerm}`);

  const encodedTerm = encodeURIComponent(searchTerm);

  try {
    // Primary URL: swiggy.com/instamart/search
    const searchUrl = `https://www.swiggy.com/instamart/search?query=${encodedTerm}`;
    console.log(`Going to: ${searchUrl}`);

    await page.goto(searchUrl, {
      waitUntil: 'domcontentloaded',
      timeout: 60000
    });

    const url = page.url();
    console.log(`Current URL: ${url}`);

    // If redirected or blocked, try again after short wait
    if (url.includes('blocked') || url.includes('captcha')) {
      console.log('Page may be blocked, waiting 3s and retrying...');
      await new Promise(r => setTimeout(r, 3000));
      await page.goto(searchUrl, {
        waitUntil: 'domcontentloaded',
        timeout: 60000
      });
    }

    return true;
  } catch (error) {
    console.log(`Error navigating to search: ${error.message}`);
    return false;
  }
}

async function ensureContentLoaded(page) {
  try {
    console.log('Ensuring Instamart content is loaded...');

    // Wait for product cards - use the correct selector from HTML analysis
    const productSelector = '[data-testid="item-collection-card-full"], [data-testid="item-collection-card"]';

    try {
      await page.waitForSelector(productSelector, {
        timeout: 15000,
        visible: true
      });
      console.log('Product cards appeared');
    } catch (e) {
      console.log(`Product cards not found within timeout: ${e.message}`);
    }

    // Extra wait for dynamic content
    await new Promise(r => setTimeout(r, 2000));

    // Count product cards
    const productCardCount = await page.evaluate(() => {
      return document.querySelectorAll(
        '[data-testid="item-collection-card-full"], [data-testid="item-collection-card"]'
      ).length;
    });

    console.log(`Found ${productCardCount} product cards on page`);

    if (productCardCount > 0) {
      return true;
    }

    // Check for "no results" message
    const noResults = await page.evaluate(() => {
      const text = document.body.innerText || '';
      return (
        text.includes('No results') ||
        text.includes('no results') ||
        text.includes('not available') ||
        text.includes('Request Blocked')
      );
    });

    if (noResults) {
      console.log('No results or blocked page detected');
      return false;
    }

    return false;
  } catch (error) {
    console.log(`Error ensuring content loaded: ${error.message}`);
    return false;
  }
}

/**
 * Intercept network responses to find the product API JSON.
 * Swiggy Instamart loads products via XHR to /mapi/ or /api/ endpoints.
 * Call this BEFORE navigating - attach the listener, then navigate.
 */
function attachProductAPIInterceptor(page, onProductData) {
  page.on('response', async (response) => {
    const url = response.url();
    const ct = response.headers()['content-type'] || '';
    if (!ct.includes('json')) return;

    // Match Swiggy's internal search API endpoints
    if (
      (url.includes('/api/instamart') || url.includes('/mapi/') || url.includes('/api/')) &&
      (url.includes('search') || url.includes('listing'))
    ) {
      try {
        const json = await response.json();
        if (json && json.data && onProductData) {
          console.log(`[API intercept] Product data from: ${url.slice(0, 100)}`);
          onProductData(json);
        }
      } catch (_) {}
    }
  });
}

/**
 * Extract products from the page HTML.
 * Uses selectors discovered from live HTML analysis.
 */
async function extractProductsFromHTML(page) {
  try {
    console.log('Extracting Instamart products from HTML structure...');

    const products = await page.evaluate(() => {
      // Try both testid variants
      let productCards = Array.from(
        document.querySelectorAll('[data-testid="item-collection-card-full"]')
      );
      if (productCards.length === 0) {
        productCards = Array.from(
          document.querySelectorAll('[data-testid="item-collection-card"]')
        );
      }

      console.log(`Found ${productCards.length} product cards`);

      return productCards.map(card => {
        try {
          const id = `instamart_${Date.now()}_${Math.random().toString(36).substring(2, 8)}`;

          // Product name: class _1lbNR
          const nameEl = card.querySelector('._1lbNR');
          const name = nameEl ? nameEl.textContent.trim() : 'Unknown Product';

          // Current price: class _2jn41 (first one - not the strikethrough)
          // The ? symbol is injected via CSS ::before, so we only get the number
          const allPriceEls = Array.from(card.querySelectorAll('._2jn41'));
          // The current price is the first one that is NOT also ._3eAjW (MRP)
          const currentPriceEl = allPriceEls.find(el => !el.classList.contains('_3eAjW'));
          const priceText = currentPriceEl ? currentPriceEl.textContent.trim() : '';
          const price = priceText ? `Rs.${priceText}` : 'Price unavailable';

          // MRP / Original price: class _3eAjW _2jn41 (strikethrough)
          const mrpEl = card.querySelector('._3eAjW._2jn41, ._1VrXB._2jn41');
          const mrpText = mrpEl ? mrpEl.textContent.trim() : '';
          const originalPrice = mrpText ? `Rs.${mrpText}` : null;

          // Savings
          let savings = null;
          if (priceText && mrpText) {
            const pVal = parseFloat(priceText);
            const mVal = parseFloat(mrpText);
            if (!isNaN(pVal) && !isNaN(mVal) && mVal > pVal) {
              savings = `Rs.${(mVal - pVal).toFixed(2)}`;
            }
          }

          // Discount text: data-testid="offer-text"
          const discountEl = card.querySelector('[data-testid="offer-text"]');
          const discount = discountEl ? discountEl.textContent.replace(/\n/g, '').trim() : null;

          // Quantity / weight: class _3wq_F
          const weightEl = card.querySelector('._3wq_F');
          let quantity = '1 item';
          if (weightEl) {
            // Remove chevron icon text
            const clone = weightEl.cloneNode(true);
            const svgEl = clone.querySelector('svg, div');
            if (svgEl) svgEl.remove();
            quantity = clone.textContent.trim() || '1 item';
          }

          // Description: class _3bM-V
          const descEl = card.querySelector('._3bM-V');
          const description = descEl ? descEl.textContent.trim() : null;

          // Image: img._16I1D or any img in card
          const imgEl = card.querySelector('img._16I1D, img[src*="instamart"]') || card.querySelector('img');
          const imageUrl = imgEl ? (imgEl.getAttribute('src') || '') : '';

          // Delivery time: aria-label="Delivery in X MINS"
          const deliveryEl = card.querySelector('[aria-label*="Delivery"]') ||
                             card.querySelector('[aria-label*="delivery"]');
          let deliveryTime = '10 mins';
          if (deliveryEl) {
            const ariaLabel = deliveryEl.getAttribute('aria-label') || '';
            const match = ariaLabel.match(/(\d+)\s*MINS?/i);
            if (match) {
              deliveryTime = `${match[1]} mins`;
            } else {
              // Try inner text
              const innerText = deliveryEl.textContent.trim();
              const innerMatch = innerText.match(/(\d+)\s*MINS?/i);
              deliveryTime = innerMatch ? `${innerMatch[1]} mins` : innerText || '10 mins';
            }
          }

          // Availability: no sold-out marker seen in live HTML; default to true
          // If out-of-stock ever appears it'll be marked
          const soldOutEl = card.querySelector('[data-testid="sold-out"], [class*="sold-out"], [class*="outOfStock"]');
          const available = !soldOutEl;

          return {
            id,
            name,
            price,
            originalPrice,
            savings,
            quantity,
            deliveryTime,
            discount,
            description,
            imageUrl,
            available,
            source: 'instamart'
          };
        } catch (err) {
          console.error('Error extracting product:', err);
          return null;
        }
      }).filter(p => p !== null && p.name !== 'Unknown Product');
    });

    console.log(`Extracted ${products.length} products from HTML`);
    return products;
  } catch (error) {
    console.error('Error in extractProductsFromHTML:', error);
    return [];
  }
}

/**
 * Main extraction function.
 * Tries JSON API response first, falls back to HTML scraping.
 */
function extractProductInformation(productJsonResponse) {
  try {
    console.log('Extracting Instamart product information...');

    // Try JSON API response (Swiggy internal API format)
    if (productJsonResponse && productJsonResponse.response) {
      const resp = productJsonResponse.response;

      // Swiggy API v2 format: response.data.cards[].card.card.info
      if (resp.data && resp.data.cards) {
        console.log('Extracting from Swiggy API v2 format...');
        const products = [];
        for (const cardWrapper of resp.data.cards) {
          try {
            const info = cardWrapper?.card?.card?.info;
            if (!info || !info.name) continue;
            products.push({
              id: info.id || `instamart_${Date.now()}_${Math.random().toString(36).substr(2, 8)}`,
              name: info.name,
              price: info.price ? `Rs.${info.price / 100}` : 'Price unavailable',
              originalPrice: info.defaultPrice ? `Rs.${info.defaultPrice / 100}` : null,
              quantity: info.quantity || info.unitInfo || '1 item',
              deliveryTime: '10 mins',
              discount: info.offerIds ? null : null,
              imageUrl: info.imageId ? `https://media-assets.swiggy.com/swiggy/image/upload/${info.imageId}` : '',
              available: !info.isInStock === false,
              source: 'instamart'
            });
          } catch (e) {}
        }
        if (products.length > 0) {
          console.log(`Extracted ${products.length} from Swiggy API v2`);
          return products;
        }
      }

      // Legacy snippet format
      if (resp.snippets) {
        console.log('Extracting from legacy snippet format...');
        const products = resp.snippets
          .filter(s => s.data && s.data.name)
          .map(s => {
            const d = s.data;
            return {
              id: (d.identity && d.identity.id) || `instamart_${Date.now()}_${Math.random().toString(36).substr(2, 8)}`,
              name: d.name,
              price: d.final_price ? `Rs.${d.final_price}` : 'Price unavailable',
              originalPrice: d.price ? `Rs.${d.price}` : null,
              quantity: d.weight || d.quantity || '1 item',
              deliveryTime: d.delivery_time || '10 mins',
              discount: d.discount_text || null,
              imageUrl: d.image_url || d.img_url || '',
              available: !d.out_of_stock,
              source: 'instamart'
            };
          });
        if (products.length > 0) {
          console.log(`Extracted ${products.length} from snippet format`);
          return products;
        }
      }
    }

    // Fallback to HTML extraction
    if (productJsonResponse && productJsonResponse.page) {
      console.log('Falling back to HTML extraction...');
      return extractProductsFromHTML(productJsonResponse.page);
    }

    return [];
  } catch (error) {
    console.error('Error in extractProductInformation:', error);
    if (productJsonResponse && productJsonResponse.page) {
      return extractProductsFromHTML(productJsonResponse.page);
    }
    return [];
  }
}

module.exports = {
  navigateToSearch,
  ensureContentLoaded,
  extractProductInformation,
  extractProductsFromHTML,
  attachProductAPIInterceptor
};
