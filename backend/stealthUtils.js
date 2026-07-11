/**
 * stealthUtils.js
 * Contains Puppeteer stealth configuration and helper functions for injecting stealth properties.
 */

const LAUNCH_ARGS = [
  "--disable-setuid-sandbox",
  "--no-sandbox",
  "--no-zygote",
  "--disable-dev-shm-usage",
  "--disable-gpu",
];

async function applyPageStealthInjections(page) {
  // Overwrite navigator.webdriver to bypass basic bot detection
  await page.evaluateOnNewDocument(() => {
    Object.defineProperty(navigator, 'webdriver', {
      get: () => undefined,
    });
  });

  // Mock chrome object
  await page.evaluateOnNewDocument(() => {
    window.chrome = {
      runtime: {},
    };
  });

  // Mock plugins length
  await page.evaluateOnNewDocument(() => {
    Object.defineProperty(navigator, 'plugins', {
      get: () => [1, 2, 3, 4, 5],
    });
  });
}

module.exports = {
  LAUNCH_ARGS,
  applyPageStealthInjections,
};
