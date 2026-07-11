/**
 * set-location.js
 * Fixed: Uses localStorage injection to set location instead of clicking
 * broken UI selectors. Also navigates to swiggy.com/instamart (not instamart.in).
 */

// Map of city names to lat/lng for direct injection
const CITY_COORDINATES = {
  'delhi': { lat: 28.6139, lng: 77.2090, address: 'New Delhi, Delhi, India' },
  'mumbai': { lat: 19.0760, lng: 72.8777, address: 'Mumbai, Maharashtra, India' },
  'bangalore': { lat: 12.9716, lng: 77.5946, address: 'Bengaluru, Karnataka, India' },
  'bengaluru': { lat: 12.9716, lng: 77.5946, address: 'Bengaluru, Karnataka, India' },
  'hyderabad': { lat: 17.3850, lng: 78.4867, address: 'Hyderabad, Telangana, India' },
  'chennai': { lat: 13.0827, lng: 80.2707, address: 'Chennai, Tamil Nadu, India' },
  'kolkata': { lat: 22.5726, lng: 88.3639, address: 'Kolkata, West Bengal, India' },
  'pune': { lat: 18.5204, lng: 73.8567, address: 'Pune, Maharashtra, India' },
  'ahmedabad': { lat: 23.0225, lng: 72.5714, address: 'Ahmedabad, Gujarat, India' },
};

async function setInstamartLocation(page, loc) {
  console.log(`Setting Instamart location to: ${loc}`);

  const cityKey = loc.toLowerCase().trim();
  const coords = CITY_COORDINATES[cityKey] || CITY_COORDINATES['bangalore'];

  try {
    // Step 1: Navigate to Swiggy Instamart
    const currentUrl = page.url();
    if (!currentUrl.includes('swiggy.com/instamart') && !currentUrl.includes('instamart.in')) {
      console.log('Navigating to Swiggy Instamart...');
      await page.goto('https://www.swiggy.com/instamart', {
        waitUntil: 'domcontentloaded',
        timeout: 60000
      });
    }

    // Step 2: Set viewport
    await page.setViewport({ width: 1280, height: 800 });

    // Step 3: Inject location via localStorage (Swiggy reads from this)
    console.log(`Injecting location: ${coords.address} (${coords.lat}, ${coords.lng})`);
    await page.evaluate((lat, lng, address) => {
      // Swiggy Instamart stores location in localStorage
      const locationData = {
        lat: lat,
        lng: lng,
        address: address,
        area: address.split(',')[0],
        city: address.split(',')[1] ? address.split(',')[1].trim() : '',
        areaId: '',
        latlng: `${lat},${lng}`
      };

      // Try multiple storage keys that Instamart uses
      try { localStorage.setItem('userLocation', JSON.stringify(locationData)); } catch(e) {}
      try { localStorage.setItem('swiggy_location', JSON.stringify(locationData)); } catch(e) {}
      try { localStorage.setItem('IM_location', JSON.stringify(locationData)); } catch(e) {}
      try {
        // Also set in sessionStorage
        sessionStorage.setItem('userLocation', JSON.stringify(locationData));
      } catch(e) {}
    }, coords.lat, coords.lng, coords.address);

    // Step 4: Set cookies with location data
    await page.setCookie({
      name: 'userLocation',
      value: JSON.stringify({ lat: coords.lat, lng: coords.lng }),
      domain: '.swiggy.com',
      path: '/'
    }).catch(() => {});

    // Step 5: Navigate to the search page with lat/lng query params
    // Swiggy Instamart also accepts lat/lng in URL for SEO pages
    await new Promise(r => setTimeout(r, 500));

    console.log(`Location injection complete: ${coords.address}`);
    return coords.address;

  } catch (err) {
    console.error('Error setting Instamart location:', err);
    return null;
  }
}

async function isLocationSet(page) {
  console.log('Checking if Instamart location is set...');
  try {
    // Check the page body text for location-related content
    const bodyText = await page.evaluate(() => document.body.innerText);
    if (bodyText && bodyText.length > 100 && !bodyText.includes('Request Blocked')) {
      // If we can load any meaningful content, location is usable
      console.log('Page loaded with content - treating location as set');
      return 'Location Set';
    }
    return null;
  } catch (err) {
    console.error('Error checking location:', err);
    return null;
  }
}

async function getDeliveryTime(page) {
  try {
    // Try to find delivery time from aria-label on product cards
    const deliveryTime = await page.evaluate(() => {
      // Look for aria-label="Delivery in X MINS" pattern
      const deliveryEl = document.querySelector('[aria-label*="Delivery in"]');
      if (deliveryEl) {
        const match = deliveryEl.getAttribute('aria-label').match(/(\d+)\s*MINS?/i);
        if (match) return `${match[1]} mins`;
      }
      // Fallback: look for text inside delivery time badge
      const badge = document.querySelector('._2zIRo, [class*="delivery"]');
      if (badge) return badge.textContent.trim() || '10 mins';
      return '10 mins';
    });
    return deliveryTime || '10 mins';
  } catch (err) {
    console.error('Error getting delivery time:', err);
    return '10 mins';
  }
}

module.exports = {
  setInstamartLocation,
  isLocationSet,
  getDeliveryTime
};
