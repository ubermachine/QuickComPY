async function navigateToSearch(page, searchTerm) {
  console.log(`Directly navigating to Bigbasket search URL with term: ${searchTerm}`);
  try {
    const encSearchTerm = encodeURIComponent(searchTerm);
    console.log(`Going to: https://www.bigbasket.com/ps/?q=${encSearchTerm}`);
    await page.goto(`https://www.bigbasket.com/ps/?q=${encSearchTerm}`, {
      waitUntil: 'domcontentloaded',
      timeout: 60000
    });
    await new Promise(r => setTimeout(r, 2000));
    return true;
  } catch (err) {
    console.log(`Error navigating to Bigbasket search: ${err.message}`);
    return false;
  }
}

async function ensureContentLoaded(page) {
  try {
    // Wait for either the product cards or the empty search page to appear
    const selectors = [
      'li[class*="PaginateItems"]',
      'div[class*="ProductTemplate"]',
      'div[class*="ColStyled"]',
      'input[placeholder="Search for Products..."]'
    ];

    let found = false;
    for (const sel of selectors) {
      try {
        await page.waitForSelector(sel, { timeout: 5000 });
        console.log(`Found Bigbasket content selector: ${sel}`);
        found = true;
        break;
      } catch (e) {
        // Try next
      }
    }
    return found;
  } catch (err) {
    console.log(`Error waiting for Bigbasket content: ${err.message}`);
    return true;
  }
}

function extractProductInformation(prodJsonOrPage) {
  console.log("Bigbasket extraction started...");
  if (prodJsonOrPage && prodJsonOrPage.useHtmlExtraction) {
    return extractProductsFromHTML(prodJsonOrPage.page);
  }
  return extractProductsFromJSON(prodJsonOrPage);
}

function extractProductsFromJSON(json) {
  console.log("Extracting Bigbasket products from JSON response...");
  const products = [];
  try {
    if (!json || !json.tabs || !Array.isArray(json.tabs) || json.tabs.length === 0) {
      console.error("Invalid Bigbasket JSON response structure");
      return products;
    }

    const tab = json.tabs[0];
    if (!tab.product_info || !Array.isArray(tab.product_info.products)) {
      console.error("No products array found in Bigbasket JSON tab");
      return products;
    }

    const rawProducts = tab.product_info.products;
    rawProducts.forEach((p, idx) => {
      try {
        const id = p.id ? String(p.id) : `bb_${idx}`;
        const name = p.desc || "Product Name Not Available";
        const quantity = p.w || "";
        
        let price = "Price Not Available";
        let originalPrice = null;
        let savings = null;
        let discount = null;

        if (p.pricing && p.pricing.discount) {
          const discountInfo = p.pricing.discount;
          if (discountInfo.prim_price && discountInfo.prim_price.sp) {
            price = `₹${discountInfo.prim_price.sp}`;
          }
          if (discountInfo.mrp) {
            originalPrice = `₹${discountInfo.mrp}`;
            
            // Calculate savings
            const spVal = discountInfo.prim_price && discountInfo.prim_price.sp ? parseFloat(discountInfo.prim_price.sp) : null;
            const mrpVal = parseFloat(discountInfo.mrp);
            if (spVal && mrpVal && mrpVal > spVal) {
              savings = `₹${(mrpVal - spVal).toFixed(2)}`;
              discount = `${Math.round(((mrpVal - spVal) / mrpVal) * 100)}% OFF`;
            }
          }
        }

        let imageUrl = "";
        if (p.images && p.images.length > 0) {
          imageUrl = p.images[0].s || "";
        }

        const deliveryTime = p.availability && p.availability.short_eta ? p.availability.short_eta : "Standard Delivery";
        const available = p.availability && p.availability.avail_status === "001";

        products.push({
          id,
          name,
          price,
          originalPrice,
          savings,
          quantity,
          deliveryTime,
          discount,
          imageUrl,
          available,
          source: "bigbasket"
        });
      } catch (err) {
        console.error("Error parsing individual Bigbasket JSON product:", err);
      }
    });

    console.log(`Successfully parsed ${products.length} products from Bigbasket JSON`);
  } catch (err) {
    console.error("Error parsing Bigbasket JSON response:", err);
  }
  return products;
}

async function extractProductsFromHTML(page) {
  console.log("Extracting Bigbasket products from HTML...");
  try {
    const products = await page.evaluate(() => {
      // Find all elements that look like product cards
      const cards = Array.from(document.querySelectorAll('li[class*="PaginateItems"], div[class*="ProductTemplate"]'));
      return cards.map((card, idx) => {
        try {
          // Find description / name
          const nameEl = card.querySelector('h3, [class*="ProductTitle"], a[class*="prod-name"]');
          const name = nameEl ? nameEl.textContent.trim() : "Product Name Not Available";

          // Find weight / quantity
          const qtyEl = card.querySelector('span[class*="PackSize"], [class*="w-full inline text-sm"]');
          const quantity = qtyEl ? qtyEl.textContent.trim() : "";

          // Find image
          const imgEl = card.querySelector('img');
          const imageUrl = imgEl ? imgEl.getAttribute('src') || imgEl.getAttribute('data-src') || "" : "";

          // Find prices
          const spEl = card.querySelector('[class*="PricingDetail__Price"], td[class*="sp"]');
          const spText = spEl ? spEl.textContent.trim() : "";
          const price = spText ? (spText.includes('₹') ? spText : `₹${spText}`) : "Price Not Available";

          const mrpEl = card.querySelector('[class*="PricingDetail__Mrp"], td[class*="mrp"]');
          const mrpText = mrpEl ? mrpEl.textContent.trim() : "";
          const originalPrice = mrpText ? (mrpText.includes('₹') ? mrpText : `₹${mrpText}`) : null;

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

          // Delivery ETA
          const etaEl = card.querySelector('[class*="eta"], [class*="DeliveryTime"]');
          const deliveryTime = etaEl ? etaEl.textContent.trim() : "Standard Delivery";

          const soldOut = card.querySelector('[class*="SoldOut"], button[disabled]');
          const available = !soldOut;

          return {
            id: `bb_html_${idx}`,
            name,
            price,
            originalPrice,
            savings,
            quantity,
            deliveryTime,
            discount,
            imageUrl,
            available,
            source: "bigbasket"
          };
        } catch (e) {
          return null;
        }
      }).filter(p => p !== null);
    });

    console.log(`Extracted ${products.length} products from Bigbasket HTML`);
    return products;
  } catch (err) {
    console.error("Error extracting products from Bigbasket HTML:", err);
    return [];
  }
}

module.exports = {
  navigateToSearch,
  ensureContentLoaded,
  extractProductInformation
};
