import urllib.parse
import asyncio
import json
import time
import zendriver as zd

# Pincode-to-coordinate mapping for location injection
PINCODE_COORDINATES = {
    '201306': {'lat': 28.5147, 'lng': 77.4855, 'address': 'Noida, Uttar Pradesh, India'},
    '201301': {'lat': 28.5355, 'lng': 77.3910, 'address': 'Noida, Uttar Pradesh, India'},
    '400001': {'lat': 19.0760, 'lng': 72.8777, 'address': 'Mumbai, Maharashtra, India'},
    '110001': {'lat': 28.6139, 'lng': 77.2090, 'address': 'New Delhi, Delhi, India'},
    '560001': {'lat': 12.9716, 'lng': 77.5946, 'address': 'Bengaluru, Karnataka, India'},
    '500001': {'lat': 17.3850, 'lng': 78.4867, 'address': 'Hyderabad, Telangana, India'},
    '600001': {'lat': 13.0827, 'lng': 80.2707, 'address': 'Chennai, Tamil Nadu, India'},
    '700001': {'lat': 22.5726, 'lng': 88.3639, 'address': 'Kolkata, West Bengal, India'},
    '411001': {'lat': 18.5204, 'lng': 73.8567, 'address': 'Pune, Maharashtra, India'},
    '380001': {'lat': 23.0225, 'lng': 72.5714, 'address': 'Ahmedabad, Gujarat, India'},
}

# City name fallback mapping
CITY_COORDINATES = {
    'noida': PINCODE_COORDINATES['201306'],
    'delhi': PINCODE_COORDINATES['110001'],
    'mumbai': PINCODE_COORDINATES['400001'],
    'bangalore': PINCODE_COORDINATES['560001'],
    'bengaluru': PINCODE_COORDINATES['560001'],
    'hyderabad': PINCODE_COORDINATES['500001'],
    'chennai': PINCODE_COORDINATES['600001'],
    'kolkata': PINCODE_COORDINATES['700001'],
    'pune': PINCODE_COORDINATES['411001'],
    'ahmedabad': PINCODE_COORDINATES['380001'],
}

# Swiggy CDN image base URL
SWIGGY_IMG_CDN = "https://instamart-media-assets.swiggy.com/swiggy/image/upload/fl_lossy,f_auto,q_auto,h_300/"


async def set_location(page, location):
    """Inject location directly into localStorage and cookies to bypass UI modals."""
    print(f"[Instamart] Setting location for {location}")
    location_key = location.lower().strip()

    # Try pincode first, then city name fallback
    coords = PINCODE_COORDINATES.get(location_key)
    if not coords:
        coords = CITY_COORDINATES.get(location_key, PINCODE_COORDINATES['560001'])

    try:
        # Navigate to Swiggy first to establish origin context for localStorage
        await page.get("https://www.swiggy.com/instamart")
        await asyncio.sleep(2)

        # Inject location into all known localStorage keys
        script = f"""
        (() => {{
            const lat = {coords['lat']};
            const lng = {coords['lng']};
            const address = "{coords['address']}";
            const locationData = {{
                lat: lat, lng: lng, address: address,
                area: address.split(',')[0],
                city: address.split(',')[1] ? address.split(',')[1].trim() : '',
                areaId: '', latlng: `${{lat}},${{lng}}`
            }};
            try {{ localStorage.setItem('userLocation', JSON.stringify(locationData)); }} catch(e) {{}}
            try {{ localStorage.setItem('swiggy_location', JSON.stringify(locationData)); }} catch(e) {{}}
            try {{ localStorage.setItem('IM_location', JSON.stringify(locationData)); }} catch(e) {{}}
            try {{ sessionStorage.setItem('userLocation', JSON.stringify(locationData)); }} catch(e) {{}}
        }})()
        """
        await page.evaluate(script)

        # Also set the cookie
        await page.send(zd.cdp.network.set_cookie(
            name='userLocation',
            value=json.dumps({'lat': coords['lat'], 'lng': coords['lng']}),
            domain='.swiggy.com',
            path='/'
        ))
        print(f"[Instamart] Location injected: lat={coords['lat']}, lng={coords['lng']}")
        return True
    except Exception as e:
        print(f"[Instamart] Location set error: {e}")
        return False


async def search(page, search_term):
    """
    Search Instamart by intercepting the internal /api/instamart/search/v2 JSON response.
    This completely bypasses AWS WAF challenges since we let the browser handle the
    WAF token negotiation natively and just read the JSON payload from the API response.
    """
    encoded = urllib.parse.quote(search_term)
    print(f"[Instamart] Searching for: {search_term}")

    collected_products = []
    resolved = {"done": False}
    target_requests = set()

    async def handle_response(event):
        if resolved["done"]:
            return
        if event.response.mime_type != "application/json":
            return
        # Match the Instamart search API endpoint
        if "api/instamart/search" in event.response.url:
            target_requests.add(event.request_id)
            print(f"[Instamart DEBUG] Intercepted search API: {event.response.url[:100]}")

    async def handle_loading_finished(event):
        if resolved["done"]:
            return
        if event.request_id not in target_requests:
            return
        try:
            body_info = await page.send(zd.cdp.network.get_response_body(request_id=event.request_id))
            if not body_info:
                return

            json_data = json.loads(body_info[0])
            cards = json_data.get("data", {}).get("cards", [])

            for card_wrapper in cards:
                card = card_wrapper.get("card", {}).get("card", {})
                card_type = card.get("@type", "")

                # Only process GridWidget cards (they contain products)
                if "GridWidget" not in card_type:
                    continue

                items = card.get("gridElements", {}).get("infoWithStyle", {}).get("items", [])
                for item in items:
                    try:
                        display_name = item.get("displayName", "Unknown")

                        # Get the first variation for price/image/quantity info
                        variations = item.get("variations", [])
                        if not variations:
                            continue
                        var = variations[0]

                        # Price extraction
                        price_obj = var.get("price", {})
                        offer_price = price_obj.get("offerPrice", {})
                        mrp_price = price_obj.get("mrp", {})

                        sp = offer_price.get("units", "")
                        mrp = mrp_price.get("units", "")

                        price = f"\u20b9{sp}" if sp else "N/A"
                        orig_price = f"\u20b9{mrp}" if mrp and str(mrp) != str(sp) else None

                        # Discount
                        discount = None
                        offer_applied = price_obj.get("offerApplied", {})
                        if offer_applied:
                            discount = offer_applied.get("listingDescription", None)

                        # Savings
                        savings = None
                        if sp and mrp:
                            try:
                                f_sp, f_mrp = float(sp), float(mrp)
                                if f_mrp > f_sp:
                                    savings = f"\u20b9{int(f_mrp - f_sp)}"
                            except Exception:
                                pass

                        # Quantity
                        quantity = var.get("quantityDescription", "1 item")

                        # Image URL from media IDs
                        image_ids = var.get("imageIds", [])
                        image_url = f"{SWIGGY_IMG_CDN}{image_ids[0]}" if image_ids else ""

                        # Availability
                        available = item.get("inStock", True) and item.get("isAvail", True)

                        # Deduplicate
                        if any(p['name'] == display_name for p in collected_products):
                            continue

                        collected_products.append({
                            "id": f"im_{var.get('skuId', len(collected_products))}",
                            "name": display_name,
                            "price": price,
                            "originalPrice": orig_price,
                            "savings": savings,
                            "quantity": quantity,
                            "deliveryTime": "10-15 mins",
                            "discount": discount,
                            "imageUrl": image_url,
                            "available": available,
                            "source": "instamart"
                        })
                    except Exception as e:
                        print(f"[Instamart] Item parse error: {e}")

            if collected_products:
                print(f"[Instamart DEBUG] Found {len(collected_products)} products via API.")
                resolved["done"] = True

        except Exception as e:
            print(f"[Instamart DEBUG] Error reading response body: {e}")

    try:
        await page.send(zd.cdp.network.enable())
        # Make sure we're on swiggy first (for WAF token to be established)
        if "swiggy.com" not in (page.url or ""):
            await page.get("https://www.swiggy.com/instamart")
            await asyncio.sleep(2)
    except Exception:
        pass

    # Add handlers AFTER initial page load to avoid capturing irrelevant JSON
    page.add_handler(zd.cdp.network.ResponseReceived, handle_response)
    page.add_handler(zd.cdp.network.LoadingFinished, handle_loading_finished)

    try:
        await page.get(f"https://www.swiggy.com/instamart/search?query={encoded}")
    except Exception:
        pass

    # Wait for API response (max 15 seconds)
    for _ in range(150):
        if resolved["done"]:
            break
        await asyncio.sleep(0.1)

    page.remove_handlers(zd.cdp.network.ResponseReceived)
    page.remove_handlers(zd.cdp.network.LoadingFinished)

    return collected_products[:8]