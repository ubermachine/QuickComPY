import urllib.parse
import asyncio
import json
import re

import zendriver as zd

from . import common

LOCATION_COORDS = {
  'delhi': { 'lat': 28.6139, 'lon': 77.2090 },
  'new delhi': { 'lat': 28.6139, 'lon': 77.2090 },
  'connaught place': { 'lat': 28.6315, 'lon': 77.2167 },
  'mumbai': { 'lat': 19.0760, 'lon': 72.8777 },
  'bengaluru': { 'lat': 12.9716, 'lon': 77.5946 },
  'bangalore': { 'lat': 12.9716, 'lon': 77.5946 },
  'hyderabad': { 'lat': 17.3850, 'lon': 78.4867 },
  'pune': { 'lat': 18.5204, 'lon': 73.8567 },
  'kolkata': { 'lat': 22.5726, 'lon': 88.3639 },
  'chennai': { 'lat': 13.0827, 'lon': 80.2707 },
  'ahmedabad': { 'lat': 23.0225, 'lon': 72.5714 },
  'gurgaon': { 'lat': 28.4595, 'lon': 77.0266 },
  'gurugram': { 'lat': 28.4595, 'lon': 77.0266 },
  'noida': { 'lat': 28.5355, 'lon': 77.3910 },
  'jaipur': { 'lat': 26.9124, 'lon': 75.7873 },
  '201306': { 'lat': 28.5147, 'lon': 77.4855 },
  'supertech ecovillage 1': { 'lat': 28.5147, 'lon': 77.4855 },
  'supertech ecovillage-1': { 'lat': 28.5147, 'lon': 77.4855 },
  'supertech eco village 1': { 'lat': 28.5147, 'lon': 77.4855 },
  'supertech eco village-1': { 'lat': 28.5147, 'lon': 77.4855 },
}

def resolve_coords(location):
    if not location:
        return LOCATION_COORDS['201306']
    key = str(location).strip().lower()
    if key in LOCATION_COORDS:
        return LOCATION_COORDS[key]
    for k, v in LOCATION_COORDS.items():
        if k in key or key in k:
            return v
    return LOCATION_COORDS['201306']

async def set_location(page, location):
    print(f"[Blinkit] Attempting to set location to {location}")
    coords = resolve_coords(location)
    lat = coords['lat']
    lon = coords['lon']
    try:
        # Inject cookies using CDP Network.setCookie
        await page.send(zd.cdp.network.set_cookie(
            name='gr_1_lat', value=str(lat), domain='.blinkit.com', path='/'
        ))
        await page.send(zd.cdp.network.set_cookie(
            name='gr_1_lon', value=str(lon), domain='.blinkit.com', path='/'
        ))
        await page.send(zd.cdp.network.set_cookie(
            name='gr_1_locality', value=str(location), domain='.blinkit.com', path='/'
        ))
        print(f"[Blinkit] Cookies injected: lat={lat}, lon={lon}")

        # Best effort navigation to establish session on domain
        try:
            await page.get("https://blinkit.com/")
            await asyncio.sleep(1)
            # Inject localStorage keys
            location_obj = {
                "coords": {"lat": lat, "lon": lon},
                "locality": str(location),
                "city": "Noida",
                "display_address": {"title": str(location), "description": str(location)}
            }
            script = f"""
            try {{ localStorage.setItem('gr_1_lat', '{lat}'); }} catch(e) {{}}
            try {{ localStorage.setItem('gr_1_lon', '{lon}'); }} catch(e) {{}}
            try {{ localStorage.setItem('gr_1_locality', '{location}'); }} catch(e) {{}}
            try {{ localStorage.setItem('location', JSON.stringify({json.dumps(location_obj)})); }} catch(e) {{}}
            """
            await page.evaluate(script)
        except Exception as e:
            print(f"[Blinkit] localStorage inject warn: {e}")
            
        return True
    except Exception as e:
        print(f"[Blinkit] Location set error: {e}")
    return False

# Blinkit encodes the promised ETA in the icon filename ("15-mins.png"); the
# adjacent title text is a useless literal "earliest".
_ETA_RE = re.compile(r"/(\d+)[-_]?mins?", re.I)


def _delivery_time(raw):
    eta = raw.get("eta_tag") or {}
    icon = ((eta.get("image") or {}).get("url")) or ""
    m = _ETA_RE.search(icon)
    if m:
        return f"{m.group(1)} mins"
    text = common.clean(((eta.get("title") or {}).get("text")))
    if text and text.lower() not in ("earliest", "eta"):
        return text
    return "10-20 mins"


def _text(node):
    """Blinkit wraps every display string as {'text': ..., 'font': ...}."""
    if isinstance(node, dict):
        return common.clean(node.get("text"))
    return common.clean(node)


def extract_products(snippets):
    products = []
    for s in snippets:
        raw = s.get("data")
        if not raw:
            continue

        # Headers, carousels and pill containers ride in the same snippet list.
        if s.get("widget_type", "") == "image_text_vr_type_header":
            continue
        identity_id = (raw.get("identity") or {}).get("id")
        if not raw.get("name") or not identity_id:
            continue
        if not str(identity_id).isdigit():
            continue

        try:
            name = _text(raw.get("name"))
            if not name:
                continue

            sp = _text(raw.get("normal_price")) or raw.get("price")
            mrp = _text(raw.get("mrp"))
            price, orig_price, savings, discount = common.price_fields(sp, mrp)

            # Prefer Blinkit's own offer copy when it has one.
            offer = _text((raw.get("offer_tag") or {}).get("title"))
            if offer:
                discount = offer.replace("\n", " ")

            if "is_sold_out" in raw:
                available = not raw["is_sold_out"]
            elif "inventory" in raw:
                available = (raw.get("inventory") or 0) > 0
            else:
                available = raw.get("product_state", "available") == "available"

            products.append({
                "id": f"bk_{identity_id}",
                "name": name,
                "price": price,
                "originalPrice": orig_price,
                "savings": savings,
                "quantity": _text(raw.get("variant")) or "1 item",
                "deliveryTime": _delivery_time(raw),
                "discount": discount,
                "imageUrl": (raw.get("image") or {}).get("url", ""),
                "available": available,
                "source": "blinkit",
            })
        except Exception as e:
            print(f"[Blinkit] snippet parse error: {type(e).__name__}: {e}")
    return products


def _parse(payload):
    snippets = (payload.get("response") or {}).get("snippets") or []
    return extract_products(snippets)


async def search(page, search_term):
    encoded = urllib.parse.quote(search_term)
    print(f"[Blinkit] Searching for: {search_term}")

    async def attempt():
        return await common.intercept_json(
            page,
            tag="Blinkit",
            # The paginated follow-up (offset=...) uses the same path, so a
            # plain substring match picks up both pages of results.
            match=lambda url: "blinkit.com/v1/layout/search" in url,
            parse=_parse,
            navigate=f"https://blinkit.com/s/?q={encoded}",
            timeout=15.0,
        )

    return await common.run_search(page, search_term, attempt, tag="Blinkit")
