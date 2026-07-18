import pathlib

p = pathlib.Path('backend_py/scrapers/jiomart.py')
content = p.read_bytes()

old = (
    b'        return await page.evaluate("""\n'
    b'        (() => {\n'
    b"            const products = [];\n"
    b"            const cards = document.querySelectorAll('.productCard__cardWrapper, .plp-card');\n"
    b"            cards.forEach((card, idx) => {\n"
    b"                try {\n"
    b"                    if (card.className && card.className.includes('Skeleton')) return;\n"
    b"                    \n"
    b"                    const nameEl = card.querySelector('.productCard__productTitle, .plp-card-title, h3');\n"
    b"                    const name = nameEl ? nameEl.textContent.trim() : 'Unknown';\n"
    b"                    if (!name || name === 'Unknown') return;\n"
    b"                    \n"
    b"                    const priceEl = card.querySelector('.PriceContainer__currentPrice, .plp-card-price, .jm-price');\n"
    b"                    const price = priceEl ? priceEl.textContent.trim() : 'N/A';\n"
    b"                    \n"
    b"                    const origEl = card.querySelector('.PriceContainer__originalPrice, .plp-card-mrp, .jm-mrp');\n"
    b"                    const origPrice = origEl ? origEl.textContent.trim() : null;\n"
    b"                    \n"
    b"                    const qtyEl = card.querySelector('.productCard__sizeSpan, .productCard__quantitySelector, .plp-card-qty');\n"
    b"                    const quantity = qtyEl ? qtyEl.textContent.trim() : '';\n"
    b"                    \n"
    b"                    const imgEl = card.querySelector('.productCard__productImage, img');\n"
    b"                    const imageUrl = imgEl ? (imgEl.src || imgEl.getAttribute('data-src') || '') : '';\n"
    b"                    \n"
    b"                    let savings = null;\n"
    b"                    let discount = null;\n"
    b"                    if (price && origPrice) {\n"
    b"                        const spVal = parseFloat(price.replace(/[^0-9.]/g, ''));\n"
    b"                        const mrpVal = parseFloat(origPrice.replace(/[^0-9.]/g, ''));\n"
    b"                        if (mrpVal > spVal) {\n"
    b"                            savings = '\u20b9' + (mrpVal - spVal).toFixed(2);\n"
    b"                            discount = Math.round(((mrpVal - spVal) / mrpVal) * 100) + '% OFF';\n"
    b"                        }\n"
    b"                    }\n"
    b"                    \n"
    b"                    products.push({\n"
    b"                        id: 'jm_' + idx,\n"
    b"                        name,\n"
    b"                        price,\n"
    b"                        originalPrice: origPrice,\n"
    b"                        savings,\n"
    b"                        quantity,\n"
    b'                        deliveryTime: "Standard Delivery",\n'
    b"                        discount,\n"
    b"                        imageUrl,\n"
    b"                        available: true,\n"
    b"                        source: 'jiomart'\n"
    b"                    });\n"
    b"                } catch(e) {}\n"
    b"            });\n"
    b"            return products;\n"
    b"        })()\n"
    b'        """)\n'
)

new = (
    b'        return await page.evaluate("""\n'
    b'        (() => {\n'
    b"            const products = [];\n"
    b"            const cards = document.querySelectorAll('.productCard__cardWrapper, .plp-card');\n"
    b"            cards.forEach((card, idx) => {\n"
    b"                try {\n"
    b"                    if (card.className && card.className.includes('Skeleton')) return;\n"
    b"                    \n"
    b"                    // Name with fallbacks\n"
    b"                    const nameEl = card.querySelector('.productCard__productTitle, .productCard__productDescription a, .plp-card-title, h3');\n"
    b"                    let name = nameEl ? nameEl.textContent.trim() : '';\n"
    b"                    if (!name) {\n"
    b"                        const altImg = card.querySelector('img[alt]');\n"
    b"                        name = altImg ? altImg.getAttribute('alt').trim() : 'Unknown';\n"
    b"                    }\n"
    b"                    if (!name || name === 'Unknown') return;\n"
    b"                    \n"
    b"                    // Price with fallbacks\n"
    b"                    const priceEl = card.querySelector('.PriceContainer__currentPrice, [class*=\"priceContainer\"] [class*=\"currentPrice\"], .plp-card-price, .jm-price');\n"
    b"                    const price = priceEl ? priceEl.textContent.trim() : 'N/A';\n"
    b"                    \n"
    b"                    const origEl = card.querySelector('.PriceContainer__originalPrice, .plp-card-mrp, .jm-mrp');\n"
    b"                    const origPrice = origEl ? origEl.textContent.trim() : null;\n"
    b"                    \n"
    b"                    const qtyEl = card.querySelector('.productCard__sizeSpan, .productCard__quantitySelector, .plp-card-qty');\n"
    b"                    const quantity = qtyEl ? qtyEl.textContent.trim() : '';\n"
    b"                    \n"
    b"                    // Image with multiple fallback strategies\n"
    b"                    const imgEl = card.querySelector('.productCard__productImage, img');\n"
    b"                    let imageUrl = imgEl ? (imgEl.src || imgEl.getAttribute('data-src') || '') : '';\n"
    b"                    if (!imageUrl) {\n"
    b"                        const srcEl = card.querySelector('source[srcset]');\n"
    b"                        if (srcEl) {\n"
    b"                            const srcset = srcEl.getAttribute('srcset');\n"
    b"                            if (srcset) imageUrl = srcset.split(',')[0].trim().split(' ')[0];\n"
    b"                        }\n"
    b"                    }\n"
    b"                    if (!imageUrl) {\n"
    b"                        const dataImg = card.querySelector('img[data-src]');\n"
    b"                        if (dataImg) imageUrl = dataImg.getAttribute('data-src') || '';\n"
    b"                    }\n"
    b"                    \n"
    b"                    let savings = null;\n"
    b"                    let discount = null;\n"
    b"                    if (price && origPrice) {\n"
    b"                        const spVal = parseFloat(price.replace(/[^0-9.]/g, ''));\n"
    b"                        const mrpVal = parseFloat(origPrice.replace(/[^0-9.]/g, ''));\n"
    b"                        if (mrpVal > spVal) {\n"
    b"                            savings = '\u20b9' + (mrpVal - spVal).toFixed(2);\n"
    b"                            discount = Math.round(((mrpVal - spVal) / mrpVal) * 100) + '% OFF';\n"
    b"                        }\n"
    b"                    }\n"
    b"                    \n"
    b"                    products.push({\n"
    b"                        id: 'jm_' + idx,\n"
    b"                        name,\n"
    b"                        price,\n"
    b"                        originalPrice: origPrice,\n"
    b"                        savings,\n"
    b"                        quantity,\n"
    b'                        deliveryTime: "Standard Delivery",\n'
    b"                        discount,\n"
    b"                        imageUrl,\n"
    b"                        available: true,\n"
    b"                        source: 'jiomart'\n"
    b"                    });\n"
    b"                } catch(e) {}\n"
    b"            });\n"
    b"            return products;\n"
    b"        })()\n"
    b'        """)\n'
)

count = content.count(old)
print(f'Found {count} occurrence(s)')
if count > 0:
    content = content.replace(old, new, 1)
    p.write_bytes(content)
    print('Done - extract_from_html updated')
else:
    # Debug: find the evaluate call
    idx = content.find(b'return await page.evaluate("""')
    if idx >= 0:
        print('Found evaluate at byte', idx)
        end = content.find(b'""")', idx)
        print('Ends at byte', end)
        chunk = content[idx:end+4]
        print('Old block repr:')
        print(repr(chunk))
        # Show length
        print(f'Block length: {len(chunk)}')
    else:
        print('evaluate(""") not found')
        idx2 = content.find(b'extract_from_html')
        if idx2 >= 0:
            chunk = content[idx2:idx2+500]
            print('Context:', repr(chunk))
