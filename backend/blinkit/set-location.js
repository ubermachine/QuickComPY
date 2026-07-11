/**
 * set-location.js — Blinkit location setting via API interception
 *
 * Strategy: Instead of clicking DOM elements (which fail under bot detection),
 * we use the following discovered APIs:
 *
 *   1. GET /visibility?latitude={lat}&longitude={lon}
 *      → Confirms if the area is serviceable
 *        Response: { success, serviceable, merchants: [{id, ...}] }
 *
 *   2. GET /location/info?lat={lat}&lon={lon}&is_pin_moved=false
 *      → Returns location metadata including locality name, city, etc.
 *        Response: { locality, city, display_address: { title, description } }
 *
 * Location is "set" by injecting lat/lon into the browser via:
 *   - localStorage keys: gr_1_lat, gr_1_lon, gr_1_locality, location
 *   - Cookies: gr_1_lat, gr_1_lon, gr_1_locality (set by navigating with ?lat=&lon= params)
 *
 * We also intercept the /location/info response to confirm the readable locality title.
 *
 * GEOCODING: We accept either:
 *   - A lat/lon object: { lat: 28.6139, lon: 77.2090 }
 *   - A location string (city/area name): resolved to coordinates via a lookup table.
 *     For production, integrate a geocoding API (e.g., Google Maps Geocoding API).
 */

// ─── Location name → lat/lon lookup (extend as needed) ─────────────────────
const LOCATION_COORDS = {
  'delhi': { lat: 28.6139, lon: 77.2090 },
  'new delhi': { lat: 28.6139, lon: 77.2090 },
  'connaught place': { lat: 28.6315, lon: 77.2167 },
  'mumbai': { lat: 19.0760, lon: 72.8777 },
  'bengaluru': { lat: 12.9716, lon: 77.5946 },
  'bangalore': { lat: 12.9716, lon: 77.5946 },
  'hyderabad': { lat: 17.3850, lon: 78.4867 },
  'pune': { lat: 18.5204, lon: 73.8567 },
  'kolkata': { lat: 22.5726, lon: 88.3639 },
  'chennai': { lat: 13.0827, lon: 80.2707 },
  'ahmedabad': { lat: 23.0225, lon: 72.5714 },
  'gurgaon': { lat: 28.4595, lon: 77.0266 },
  'gurugram': { lat: 28.4595, lon: 77.0266 },
  'noida': { lat: 28.5355, lon: 77.3910 },
  'jaipur': { lat: 26.9124, lon: 75.7873 },
};

function resolveCoords(location) {
  if (location && typeof location === 'object' && location.lat !== undefined) {
    return { lat: location.lat, lon: location.lon };
  }
  if (typeof location === 'string') {
    const key = location.trim().toLowerCase();
    if (LOCATION_COORDS[key]) return LOCATION_COORDS[key];
    // Fallback: try partial match
    for (const [name, coords] of Object.entries(LOCATION_COORDS)) {
      if (key.includes(name) || name.includes(key)) return coords;
    }
  }
  return null;
}

/**
 * Sets the Blinkit location by injecting coordinates into the browser session.
 *
 * @param {Page} page - Puppeteer page object (must already be on blinkit.com)
 * @param {string|{lat,lon}} location - City name or coordinate object
 * @returns {string|null} The resolved locality name, or null on failure
 */
async function setBlinkitLocation(page, location) {
  console.log(`[setBlinkitLocation] Setting location to: ${JSON.stringify(location)}`);

  const coords = resolveCoords(location);
  if (!coords) {
    console.error(`[setBlinkitLocation] Could not resolve coordinates for: ${location}`);
    return null;
  }

  const { lat, lon } = coords;
  console.log(`[setBlinkitLocation] Using coordinates: lat=${lat}, lon=${lon}`);

  try {
    // Ensure we are on blinkit.com
    if (!page.url().includes('blinkit.com')) {
      await page.goto('https://blinkit.com/', {
        waitUntil: 'domcontentloaded',
        timeout: 60000,
      });
      await delay(2000);
    }

    // Set up a listener for /location/info to capture the locality name
    let locationTitle = null;
    const locationPromise = new Promise((resolve) => {
      const handler = async (response) => {
        const url = response.url();
        if (!url.includes('blinkit.com/location/info')) return;
        try {
          const json = await response.json();
          if (json && json.display_address && json.display_address.title) {
            locationTitle = json.display_address.title;
            page.off('response', handler);
            resolve(locationTitle);
          } else if (json && json.locality) {
            locationTitle = json.locality;
            page.off('response', handler);
            resolve(locationTitle);
          }
        } catch (_) {}
      };
      page.on('response', handler);
      // Resolve with null after 10s if not triggered
      setTimeout(() => resolve(null), 10000);
    });

    // Navigate with lat/lon query params — this causes the site to:
    // 1. Set gr_1_lat, gr_1_lon cookies
    // 2. Call /visibility, /location/info APIs automatically
    // 3. Update the location bar
    await page.goto(`https://blinkit.com/?lat=${lat}&lon=${lon}`, {
      waitUntil: 'domcontentloaded',
      timeout: 30000,
    }).catch(e => console.log(`[setBlinkitLocation] goto warn: ${e.message}`));

    // Wait for /location/info API response
    const title = await locationPromise;

    if (title) {
      console.log(`[setBlinkitLocation] Location confirmed: "${title}"`);
      return title;
    }

    // Fallback: manually check /visibility API via in-page fetch
    const visibilityResult = await page.evaluate(async (latitude, longitude) => {
      try {
        const res = await fetch(
          `https://blinkit.com/visibility?latitude=${latitude}&longitude=${longitude}`,
          { credentials: 'include', headers: { Accept: 'application/json' } }
        );
        return await res.json();
      } catch (e) {
        return { error: e.message };
      }
    }, lat, lon);

    console.log('[setBlinkitLocation] Visibility check:', JSON.stringify(visibilityResult).slice(0, 200));

    if (visibilityResult && visibilityResult.serviceable) {
      const fallbackTitle = `${lat},${lon}`;
      console.log(`[setBlinkitLocation] Area is serviceable. Returning coords as title: ${fallbackTitle}`);
      return fallbackTitle;
    }

    console.error('[setBlinkitLocation] Area not serviceable or location check failed');
    return null;
  } catch (err) {
    console.error('[setBlinkitLocation] Error:', err.message);
    return null;
  }
}

/**
 * Checks if location is currently set by calling /visibility with the stored coords.
 * Falls back to reading localStorage for stored lat/lon.
 *
 * @param {Page} page
 * @returns {string|null} locality title if set, "400" or null otherwise
 */
async function isLocationSet(page) {
  console.log('[isLocationSet] Checking location status...');

  try {
    // Try reading location from localStorage
    const stored = await page.evaluate(() => {
      try {
        const loc = localStorage.getItem('location');
        if (loc) return JSON.parse(loc);
      } catch (_) {}
      return null;
    });

    if (stored && (stored.lat || stored.latitude)) {
      const lat = stored.lat || stored.latitude;
      const lon = stored.lon || stored.longitude;
      console.log(`[isLocationSet] Found stored location: lat=${lat}, lon=${lon}`);

      const result = await page.evaluate(async (latitude, longitude) => {
        try {
          const res = await fetch(
            `https://blinkit.com/visibility?latitude=${latitude}&longitude=${longitude}`,
            { credentials: 'include', headers: { Accept: 'application/json' } }
          );
          const json = await res.json();
          return json && json.serviceable ? 'serviceable' : '400';
        } catch (_) { return '400'; }
      }, lat, lon);

      return result === 'serviceable' ? (stored.locality || `${lat},${lon}`) : '400';
    }

    // Check cookies
    const cookies = await page.cookies();
    const latCookie = cookies.find(c => c.name === 'gr_1_lat');
    const lonCookie = cookies.find(c => c.name === 'gr_1_lon');
    const localityCookie = cookies.find(c => c.name === 'gr_1_locality');

    if (latCookie && lonCookie) {
      console.log(`[isLocationSet] Found location cookies: lat=${latCookie.value}, lon=${lonCookie.value}`);
      return localityCookie ? decodeURIComponent(localityCookie.value) : `${latCookie.value},${lonCookie.value}`;
    }

    console.log('[isLocationSet] No location found in localStorage or cookies');
    return '400';
  } catch (err) {
    console.error('[isLocationSet] Error:', err.message);
    return '400';
  }
}

function delay(ms) {
  return new Promise(r => setTimeout(r, ms));
}

module.exports = {
  setBlinkitLocation,
  isLocationSet,
  resolveCoords,
  LOCATION_COORDS,
};
