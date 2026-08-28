"""Amazon.in.

The odd one out among the five quick-commerce platforms: Amazon renders its
search results server-side, so there is no private JSON API to intercept and we
read the DOM instead. Two consequences worth knowing:

  * Amazon is a general marketplace. An unscoped search for "milk" returns a
    2009 film and an MP3 album alongside milk powder, so searches are scoped to
    the grocery index first and only widened when that comes back empty.
  * Delivery is next-day-ish rather than ten minutes, so the deliveryTime field
    carries Amazon's own promise text rather than a fabricated ETA.

Unlike Swiggy, Amazon's delivery pincode really is settable: the address-change
endpoint behind the "Deliver to" control accepts a bare pincode and answers with
the resolved city, which is what set_location verifies against.
"""

import asyncio
import json
import re
import urllib.parse

from . import common

# Pincode per city, so a user typing "mumbai" gets a serviceable location.
CITY_PINCODES = {
    'delhi': '110001', 'new delhi': '110001', 'mumbai': '400001',
    'bengaluru': '560001', 'bangalore': '560001', 'hyderabad': '500001',
    'pune': '411001', 'kolkata': '700001', 'chennai': '600001',
    'ahmedabad': '380001', 'gurgaon': '122001', 'gurugram': '122001',
    'noida': '201301', 'jaipur': '302001',
}

DEFAULT_PINCODE = '201306'


def resolve_pincode(location):
    if not location:
        return DEFAULT_PINCODE
    key = str(location).strip().lower()
    if re.fullmatch(r'\d{6}', key):
        return key
    if key in CITY_PINCODES:
        return CITY_PINCODES[key]
    for name, pin in CITY_PINCODES.items():
        if name in key or key in name:
            return pin
    return DEFAULT_PINCODE


# Amazon's card markup, read in the page. The full product title lives in the
# thumbnail's alt text -- the h2 holds only the brand -- and the struck-through
# MRP must be taken from the element explicitly marked data-a-strike, because
# the looser .a-text-price selector also matches per-unit prices.
_EXTRACT_JS = """
JSON.stringify((function () {
  var cards = document.querySelectorAll('[data-component-type="s-search-result"]');
  var out = [];
  for (var i = 0; i < cards.length; i++) {
    var c = cards[i];
    function text(sel) {
      var e = c.querySelector(sel);
      return e ? e.textContent.trim() : null;
    }
    var img = c.querySelector('img.s-image');
    var title = img ? (img.getAttribute('alt') || '') : '';
    if (!title) { continue; }
    out.push({
      asin: c.getAttribute('data-asin') || '',
      title: title,
      price: text('.a-price[data-a-size] .a-offscreen') || text('.a-price .a-offscreen'),
      mrp: text('.a-price[data-a-strike="true"] .a-offscreen'),
      image: img ? img.getAttribute('src') : '',
      sponsored: !!c.querySelector('.puis-sponsored-label-text'),
      delivery: text('[data-cy="delivery-recipe"]') || '',
      unavailable: /currently unavailable|out of stock/i.test(c.textContent || '')
    });
  }
  return out;
})())
"""

# Pack size is embedded in the title ("... Body Lotion 600ml", "Powder 1kg").
_SIZE_RE = re.compile(
    r"(\d+(?:\.\d+)?\s?(?:g|gm|gms|kg|ml|l|ltr|litre|liter|pcs|pc|pack|n|count|units?)\b)",
    re.I,
)

# Amazon states two promises; the second ("fastest delivery Today 10am") is the
# one comparable to a quick-commerce ETA.
_FASTEST_RE = re.compile(r"fastest delivery\s+([^|]+?)(?:\s{2,}|$)", re.I)
_FREE_RE = re.compile(r"FREE delivery\s+([A-Za-z0-9 ,]+?)(?:\s+on\b|\s{2,}|$)", re.I)


def _delivery_time(raw):
    text = common.clean(raw)
    if not text:
        return "Standard Delivery"
    m = _FASTEST_RE.search(text)
    if m:
        return common.clean(m.group(1)) or "Standard Delivery"
    m = _FREE_RE.search(text)
    if m:
        return common.clean(m.group(1)) or "Standard Delivery"
    return "Standard Delivery"


def _quantity(title):
    m = _SIZE_RE.search(title or "")
    return common.clean(m.group(1)) if m else "1 item"


def extract_products(items):
    products = []
    for item in items:
        try:
            title = common.clean(item.get("title"))
            if not title:
                continue
            # Sponsored cards prefix the alt text; strip it so the label does
            # not pollute the name or the relevance score.
            title = re.sub(r"^sponsored ad\s*[-–]\s*", "", title, flags=re.I)

            price, orig_price, savings, discount = common.price_fields(
                item.get("price"), item.get("mrp")
            )

            products.append({
                "id": f"az_{item.get('asin') or title}",
                "name": title,
                "price": price,
                "originalPrice": orig_price,
                "savings": savings,
                "quantity": _quantity(title),
                "deliveryTime": _delivery_time(item.get("delivery")),
                "discount": discount,
                "imageUrl": item.get("image") or "",
                "available": not item.get("unavailable", False),
                "sponsored": bool(item.get("sponsored")),
                "source": "amazon",
            })
        except Exception as e:
            print(f"[Amazon] item parse error: {type(e).__name__}: {e}")

    # Amazon leads with paid placements. Drop them when organic results exist,
    # rather than merely demoting: unlike a quick-commerce grid, a sponsored
    # Amazon card is frequently a different product category altogether.
    organic = [p for p in products if not p["sponsored"]]
    chosen = organic or products
    for p in chosen:
        p.pop("sponsored", None)
    return chosen


# Address-change accepts a bare pincode and reports the city it resolved to.
_SET_PINCODE_JS = """
(async () => {
  const body = new URLSearchParams({
    locationType: 'LOCATION_INPUT',
    zipCode: '%s',
    storeContext: 'generic',
    deviceType: 'web',
    pageType: 'Search',
    actionSource: 'glow'
  });
  try {
    const r = await fetch('/portal-migration/hz/glow/address-change?actionSource=glow', {
      method: 'POST',
      credentials: 'include',
      headers: {'Content-Type': 'application/x-www-form-urlencoded'},
      body: body
    });
    const t = await r.text();
    // Reduce in the page: the full reply is long, and truncating it here would
    // hand Python a JSON fragment it cannot parse.
    let d = {};
    try { d = JSON.parse(t); } catch (e) { return JSON.stringify({parseError: t.slice(0, 160)}); }
    return JSON.stringify({
      status: r.status,
      updated: d.isAddressUpdated,
      valid: d.isValidAddress,
      successful: d.successful,
      city: (d.address || {}).city || null,
      state: (d.address || {}).state || null
    });
  } catch (e) {
    return JSON.stringify({error: String(e)});
  }
})()
"""


async def set_location(page, location):
    """Set the delivery pincode through Amazon's own address-change endpoint.

    Returns True only when Amazon confirms it accepted the pincode, so the UI's
    per-platform badge reflects something real.
    """
    pincode = resolve_pincode(location)
    print(f"[Amazon] Setting delivery pincode to {pincode}")
    try:
        await page.get("https://www.amazon.in/")
        # Amazon's landing page redirects and hydrates for a moment; evaluating
        # straight after get() races it and the CDP target vanishes mid-call.
        await asyncio.sleep(2.5)
        raw = await page.evaluate(_SET_PINCODE_JS % pincode, await_promise=True)
        try:
            data = json.loads(str(raw))
        except (ValueError, TypeError):
            print(f"[Amazon] Unexpected address-change reply: {str(raw)[:120]}")
            return False

        ok = bool(data.get("updated")) and bool(data.get("successful"))
        city = data.get("city")
        if ok:
            print(f"[Amazon] Pincode {pincode} accepted ({city or 'unknown city'})")
        else:
            print(f"[Amazon] Address change rejected for {pincode}: {str(raw)[:120]}")
        return ok
    except Exception as e:
        print(f"[Amazon] Location set error: {type(e).__name__}: {e}")
        return False


async def search(page, search_term):
    encoded = urllib.parse.quote(search_term)
    print(f"[Amazon] Searching for: {search_term}")

    async def attempt_scoped(url):
        result = await common.scrape_dom(
            page, tag="Amazon", navigate=url, extract=_EXTRACT_JS,
        )
        if result.status == common.OK:
            result.products = extract_products(result.products)
            if not result.products:
                result.status = common.EMPTY
        return result

    async def attempt():
        # Grocery first, so a marketplace-wide search does not answer "milk"
        # with a film. Widen only if that index has nothing.
        result = await attempt_scoped(
            f"https://www.amazon.in/s?k={encoded}&i=grocery"
        )
        if result.status == common.EMPTY:
            print("[Amazon] No grocery matches, widening to all departments")
            result = await attempt_scoped(f"https://www.amazon.in/s?k={encoded}")
        return result

    return await common.run_search(page, search_term, attempt, tag="Amazon")
