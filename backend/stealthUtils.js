/**
 * stealthUtils.js — Advanced anti-detection and stealth rules for Puppeteer.
 *
 * Implements:
 *   1. Modern, up-to-date Chrome User-Agent and client-hints spoofing.
 *   2. In-page overrides via page.evaluateOnNewDocument to hide automated flags.
 *   3. Custom launch argument overrides.
 */

const DEFAULT_USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36';

const DEFAULT_HEADERS = {
  'sec-ch-ua': '"Not/A)Brand";v="8", "Chromium";v="126", "Google Chrome";v="126"',
  'sec-ch-ua-mobile': '?0',
  'sec-ch-ua-platform': '"Windows"',
  'upgrade-insecure-requests': '1',
  'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
  'accept-language': 'en-US,en;q=0.9',
};

const LAUNCH_ARGS = [
  '--disable-setuid-sandbox',
  '--no-sandbox',
  '--single-process',
  '--no-zygote',
  '--disable-blink-features=AutomationControlled',
  '--disable-infobars',
  '--window-size=1280,800',
  '--ignore-certificate-errors',
  '--ignore-certificate-errors-spki-list',
  '--no-default-browser-check',
  '--disable-extensions',
];

/**
 * Injects a script into the page that executes before any other scripts
 * on the document. This is used to spoof the navigator.webdriver, mock plugins,
 * window.chrome, etc., so modern bot detectors (Cloudflare, Akamai, etc.) don't block.
 */
async function applyPageStealthInjections(page) {
  // Set consistent viewport and User-Agent
  await page.setViewport({ width: 1280, height: 800 });
  await page.setUserAgent(DEFAULT_USER_AGENT);
  await page.setExtraHTTPHeaders(DEFAULT_HEADERS);

  // Request interception to block non-essential resources for acceleration
  await page.setRequestInterception(true);
  page.on('request', (req) => {
    const resourceType = req.resourceType();
    if (['image', 'media', 'font', 'stylesheet'].includes(resourceType)) {
      req.abort().catch(() => {});
    } else {
      req.continue().catch(() => {});
    }
  });

  // Inject in-page evasion logic
  await page.evaluateOnNewDocument(() => {
    // 1. Hide Webdriver property completely
    Object.defineProperty(navigator, 'webdriver', {
      get: () => undefined,
    });

    // 2. Overwrite languages
    Object.defineProperty(navigator, 'languages', {
      get: () => ['en-US', 'en'],
    });

    // 3. Mock Chrome object
    window.chrome = {
      app: {
        isInstalled: false,
        InstallState: {
          DISABLED: 'disabled',
          INSTALLED: 'installed',
          NOT_INSTALLED: 'not_installed',
        },
        runningState: () => 'cannot_run',
        getInstallState: (cb) => { if (cb) cb('not_installed'); },
        getDetails: () => null,
      },
      runtime: {
        OnInstalledReason: {
          CHROME_UPDATE: 'chrome_update',
          INSTALL: 'install',
          SHARED_MODULE_UPDATE: 'shared_module_update',
          UPDATE: 'update',
        },
        OnRestartRequiredReason: {
          APP_UPDATE: 'app_update',
          OS_UPDATE: 'os_update',
          PERIODIC: 'periodic',
        },
        PlatformArch: {
          ARM: 'arm',
          ARM64: 'arm64',
          MIPS: 'mips',
          MIPS64: 'mips64',
          X86_32: 'x86-32',
          X86_64: 'x86-64',
        },
        PlatformNaclArch: {
          ARM: 'arm',
          MIPS: 'mips',
          MIPS64: 'mips64',
          X86_32: 'x86-32',
          X86_64: 'x86-64',
        },
        PlatformOs: {
          ANDROID: 'android',
          CROS: 'cros',
          LINUX: 'linux',
          MAC: 'mac',
          OPENBSD: 'openbsd',
          WIN: 'win',
        },
        RequestUpdateCheckStatus: {
          NO_UPDATE: 'no_update',
          THROTTLED: 'throttled',
          UPDATE_AVAILABLE: 'update_available',
        },
      },
      csi: () => {},
      loadTimes: () => {},
    };

    // 4. Mock Plugins
    const mockPlugins = [
      { name: 'PDF Viewer', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
      { name: 'Chrome PDF Viewer', filename: 'mhjcbomhhbbfomgihfkocgfcldbfgpkg', description: 'Portable Document Format' },
    ];

    const makePlugin = (p) => {
      const plugin = Object.create(Plugin.prototype);
      Object.defineProperties(plugin, {
        name: { get: () => p.name, enumerable: true },
        filename: { get: () => p.filename, enumerable: true },
        description: { get: () => p.description, enumerable: true },
        length: { get: () => 0 },
      });
      return plugin;
    };

    const pluginInstances = mockPlugins.map(makePlugin);
    const pluginArray = Object.create(PluginArray.prototype);

    Object.defineProperties(pluginArray, {
      length: { get: () => pluginInstances.length, enumerable: true },
      item: { value: (idx) => pluginInstances[idx] },
      namedItem: { value: (name) => pluginInstances.find(p => p.name === name) || null },
    });

    pluginInstances.forEach((p, idx) => {
      Object.defineProperty(pluginArray, idx, { value: p, enumerable: true });
      Object.defineProperty(pluginArray, p.name, { value: p, enumerable: true });
    });

    Object.defineProperty(navigator, 'plugins', {
      get: () => pluginArray,
    });

    // 5. Spoof permissions query
    const originalQuery = navigator.permissions.query;
    navigator.permissions.query = (parameters) => (
      parameters.name === 'notifications' ?
        Promise.resolve({ state: Notification.permission, onchange: null }) :
        originalQuery(parameters)
    );

    // 6. WebGL Vendor and Renderer Spoofing
    const getParameterProxy = (target, thisArg, argList) => {
      const param = argList[0];
      // UNMASKED_VENDOR_WEBGL
      if (param === 37445) {
        return 'Intel Inc.';
      }
      // UNMASKED_RENDERER_WEBGL
      if (param === 37446) {
        return 'Intel(R) Iris(TM) Plus Graphics 640';
      }
      return Reflect.apply(target, thisArg, argList);
    };

    const originalGetParameter = WebGLRenderingContext.prototype.getParameter;
    WebGLRenderingContext.prototype.getParameter = new Proxy(originalGetParameter, {
      apply: getParameterProxy,
    });

    if (window.WebGL2RenderingContext) {
      const originalGetParameter2 = WebGL2RenderingContext.prototype.getParameter;
      WebGL2RenderingContext.prototype.getParameter = new Proxy(originalGetParameter2, {
        apply: getParameterProxy,
      });
    }

    // 7. Prevent detection of modified prototypes/call stack on WebGL functions
    const cleanProto = (target, name) => {
      if (target.prototype && target.prototype[name]) {
        const desc = Object.getOwnPropertyDescriptor(target.prototype, name);
        if (desc && desc.value && typeof desc.value === 'function') {
          Object.defineProperty(desc.value, 'toString', {
            value: () => `function ${name}() { [native code] }`,
            writable: true,
            configurable: true,
          });
        }
      }
    };
    cleanProto(WebGLRenderingContext, 'getParameter');
    if (window.WebGL2RenderingContext) {
      cleanProto(WebGL2RenderingContext, 'getParameter');
    }
  });
}

module.exports = {
  DEFAULT_USER_AGENT,
  DEFAULT_HEADERS,
  LAUNCH_ARGS,
  applyPageStealthInjections,
};
