const express = require("express");
const http = require("http");
const ws = require("ws");
const cors = require("cors");
const puppet = require("puppeteer-extra");
const StealthPlugin = require("puppeteer-extra-plugin-stealth");
puppet.use(StealthPlugin());
const morgan = require("morgan");
const path = require("path");
require("dotenv").config();

// Define supported services
const SVCS = ["blinkit", /* "zepto", "instamart", */ "bigbasket", "jiomart"];

// Import service helpers dynamically
const svcHelpers = {};
SVCS.forEach((svc) => {
  svcHelpers[svc] = {
    search: require(`./${svc}/searchHelpers.js`),
    location: require(`./${svc}/set-location.js`),
  };
});

const app = express();
const srv = http.createServer(app);
const wss = new ws.Server({ server: srv });

// Configure CORS with options
app.use(
  cors({
    origin: process.env.FRONTEND_URL || "http://localhost:5173",
    credentials: true,
  })
);
app.use(express.json());
app.use(morgan("dev"));

// Simple static file serving
app.use(express.static(path.join(__dirname, "../public")));

// Health check endpoint
app.get("/api/health", (req, res) => {
  res.status(200).json({
    status: "ok",
    timestamp: new Date().toISOString(),
  });
});

// Global shared browser promise to avoid race conditions
let globalBrowserPromise = null;

// Client tracking maps
const browsers = new Map(); // Keep map for backward compatibility, but we use contexts or the shared browser
const pages = new Map();    // Structure: { cid: { svc: page } }
const locSet = new Map();   // Structure: { cid: { svc: bool } }

const locationSet = locSet;
const serviceHelpers = svcHelpers;

// WebSocket connection handler
wss.on("connection", (socket) => {
  const cid = Math.random().toString(36).substring(2, 15);
  console.log(`Client connected: ${cid}`);

  // Initialize client tracking
  browsers.set(cid, {});
  pages.set(cid, {});
  locSet.set(cid, {});

  // Send initial connection acknowledgment
  socket.send(JSON.stringify({ type: "connected", cid }));
  socket.on("message", async (msg) => {
    try {
      const data = JSON.parse(msg);
      const action = data.action || data.type;
      console.log(`Received message from ${cid}:`, action);

      // Validate service
      if (data.service && !SVCS.includes(data.service)) {
        return sendErr(socket, "Invalid service specified");
      }

      switch (action) {
        case "initialize":
          await handleInitialize(socket, cid, data);
          break;
        case "setLocation":
        case "set-location":
          await handleSetLocation(socket, cid, data);
          break;
        case "search":
          await handleSearch(socket, cid, data);
          break;
        case "close":
        case "close-browser":
          await handleCloseBrowser(socket, cid, data);
          break;
        default:
          sendErr(socket, `Unknown message type/action: ${action}`);
      }    } catch (err) {
      console.error("Error processing message:", err);
      sendErr(socket, err.message);
    }
  });

  // Handle client disconnection
  socket.on("close", async () => {
    console.log(`Client disconnected: ${cid}`);
    await cleanup(cid);
  });
});

// Helper function to send error messages
function sendErr(socket, msg) {
  socket.send(
    JSON.stringify({
      type: "error",
      error: msg,
    })
  );
}

// Handler functions
async function handleInitialize(ws, clientId, data) {
  ws.send(
    JSON.stringify({
      action: "statusUpdate",
      step: "initialize",
      status: "loading",
      message: "Initializing browsers for all services...",
    })
  );

  try {
    // Launch all browsers in parallel
    await Promise.all(
      SVCS.map(async (svc) => {
        const browser = await initBrowser(clientId, svc);
        await getPage(clientId, svc, browser);
      })
    );

    // Initialize location status for all services
    const initialLocationStatus = {};
    SVCS.forEach((svc) => {
      initialLocationStatus[svc] = false;
    });
    locationSet.set(clientId, initialLocationStatus);

    ws.send(
      JSON.stringify({
        action: "statusUpdate",
        step: "initialize",
        status: "completed",
        success: true,
        message: "All browsers initialized successfully.",
      })
    );
  } catch (err) {
    console.error("Error during browser initialization:", err);
    ws.send(
      JSON.stringify({
        action: "statusUpdate",
        step: "initialize",
        status: "error",
        success: false,
        message: `Failed to initialize browsers: ${err.message}`,
      })
    );
  }
}

let activeLocationPromise = null;

async function handleSetLocation(socket, cid, data) {
  const ws = socket;
  const clientId = cid;
  const pgs = pages.get(cid);
  const clientPages = pgs;
  
  if (
    !pgs ||
    SVCS.some(svc => !pgs[svc])
  ) {
    socket.send(
      JSON.stringify({
        action: "statusUpdate",
        step: "setLocation",
        status: "error",
        success: false,
        message: "Browsers not initialized. Please initialize first.",
      })
    );
    return;
  }
  const { location, services: svcs } = data;
  if (!location) {
    socket.send(
      JSON.stringify({
        action: "statusUpdate",
        step: "setLocation",
        status: "error",
        success: false,
        message: "No location provided.",
      })
    );
    return;
  }

  const servicesToUpdate =
    svcs && Array.isArray(svcs) && svcs.length > 0
      ? svcs.filter((s) => SVCS.includes(s))
      : SVCS;
  if (servicesToUpdate.length === 0) {
    socket.send(
      JSON.stringify({
        action: "statusUpdate",
        step: "setLocation",
        status: "error",
        success: false,
        message: "No valid services specified for location update.",
      })
    );
    return;
  }

  socket.send(
    JSON.stringify({
      action: "statusUpdate",
      step: "setLocation",
      status: "loading",
      message:
        servicesToUpdate.length === SVCS.length
          ? `Setting location to ${location} on all services...`
          : `Setting location to ${location} on ${servicesToUpdate.join(
              ", "
            )}...`,
    })
  );

  while (activeLocationPromise) {
    await activeLocationPromise;
  }

  let resolveLock;
  activeLocationPromise = new Promise((resolve) => {
    resolveLock = resolve;
  });

  try {
    const setLocationPromises = [];

    servicesToUpdate.forEach((svc) => {
      if (SVCS.includes(svc)) {
        setLocationPromises.push(
          (async () => {
            try {
              // Standardized setLocation or fallback to service-specific name
              const setLocFn =
                serviceHelpers[svc].location.setLocation ||
                serviceHelpers[svc].location[
                  `set${svc.charAt(0).toUpperCase() + svc.slice(1)}Location`
                ];
              const locationTitle = await setLocFn(
                clientPages[svc],
                location
              );
              return {
                service: svc,
                success: !!locationTitle,
                title: locationTitle || null,
              };
            } catch (error) {
              console.error(`Error setting ${svc} location:`, error);
              return {
                service: svc,
                success: false,
                error: error.message,
              };
            }
          })()
        );
      }
    });

    const results = await Promise.all(setLocationPromises);

    const locationStatus = locationSet.get(clientId) || {};
    SVCS.forEach((svc) => {
      if (locationStatus[svc] === undefined) {
        locationStatus[svc] = false;
      }
    });

    let anySuccess = false;
    let locationTitles = {};
    let failedServices = [];

    results.forEach((result) => {
      locationStatus[result.service] = result.success;
      if (result.success) {
        anySuccess = true;
        locationTitles[result.service] = result.title;
      } else {
        failedServices.push(result.service);
      }
    });

    locationSet.set(clientId, locationStatus);

    if (anySuccess) {
      ws.send(
        JSON.stringify({
          action: "statusUpdate",
          step: "setLocation",
          status: "completed",
          success: true,
          locationResults: results,
          failedServices: failedServices,
          message:
            failedServices.length > 0
              ? `Location set successful for some services. Failed for: ${failedServices.join(
                  ", "
                )}`
              : `Location set successful for all requested services`,
        })
      );
    } else {
      ws.send(
        JSON.stringify({
          action: "statusUpdate",
          step: "setLocation",
          status: "error",
          success: false,
          locationResults: results,
          failedServices: failedServices, // Include the list of failed services for retry
          message: `Failed to set location on any service: ${failedServices.join(
            ", "
          )}. Please try again.`,
        })
      );
    }
  } catch (error) {
    console.error("Error in location setting process:", error);
    ws.send(
      JSON.stringify({
        action: "statusUpdate",
        step: "setLocation",
        status: "error",
        success: false,
        message: `Error setting locations: ${error.message}`,
      })
    );
  } finally {
    activeLocationPromise = null;
    if (resolveLock) resolveLock();
  }
}

async function handleSearch(ws, clientId, data) {
  const searchPages = pages.get(clientId);
  const locationStatus = locationSet.get(clientId) || {};
  SVCS.forEach((svc) => {
    if (locationStatus[svc] === undefined) {
      locationStatus[svc] = false;
    }
  });

  if (
    !searchPages ||
    SVCS.some(svc => !searchPages[svc])
  ) {
    ws.send(
      JSON.stringify({
        action: "statusUpdate",
        step: "search",
        status: "error",
        success: false,
        message: "Browsers not initialized. Please initialize first.",
      })
    );
    return;
  }

  const { searchTerm } = data;
  if (!searchTerm) {
    ws.send(
      JSON.stringify({
        action: "statusUpdate",
        step: "search",
        status: "skipped",
        success: false,
        message: "No search term provided.",
      })
    );
    ws.send(
      JSON.stringify({
        status: "info",
        action: "searchResults",
        products: (() => {
          const emptyProducts = {};
          SVCS.forEach((s) => (emptyProducts[s] = []));
          return emptyProducts;
        })(),
        message: "Please provide a search term.",
      })
    );
    return;
  }

  // Check if any service has location set
  const anyLocationSet = SVCS.some((svc) => locationStatus[svc]);
  if (!anyLocationSet) {
    ws.send(
      JSON.stringify({
        action: "statusUpdate",
        step: "search",
        status: "error",
        success: false,
        message:
          "Location not set on any service. Please set location first.",
      })
    );
    return;
  }

  // Notify that search is starting
  ws.send(
    JSON.stringify({
      action: "statusUpdate",
      step: "search",
      status: "loading",
      message: `Searching for "${searchTerm}" across all services...`,
    })
  );

  // Search on each service in parallel
  const searchResults = {};
  SVCS.forEach((svc) => {
    searchResults[svc] = { status: "pending", products: [] };
  });

  // Function to send search progress updates for individual services
  const updateSearchStatus = (
    service,
    status,
    message,
    products = null
  ) => {
    searchResults[service] = {
      status,
      message,
      products: products || searchResults[service].products,
    };

    ws.send(
      JSON.stringify({
        action: "serviceSearchUpdate",
        service,
        status,
        message,
        hasProducts: products ? products.length > 0 : false,
        products: products || [],
      })
    );
  };

  // Function to run search for a specific service
  const runServiceSearch = async (
    service,
    page,
    navigateToSearch,
    ensureContentLoaded,
    extractProductInformation
  ) => {
    if (!locationStatus[service]) {
      updateSearchStatus(
        service,
        "skipped",
        `Location not set for ${service}.`
      );
      return [];
    }

    updateSearchStatus(
      service,
      "loading",
      `Searching on ${service}...`
    );

    try {
      // Navigate to the search page
      updateSearchStatus(
        service,
        "navigating",
        `Navigating to ${service} search...`
      );

      let productJsonResponse = null;

      if (service === "jiomart") {
        const navigationSuccess = await navigateToSearch(page, searchTerm);
        if (!navigationSuccess) {
          updateSearchStatus(
            service,
            "error",
            `Failed to navigate to ${service} search page.`
          );
          return [];
        }

        updateSearchStatus(
          service,
          "loading_content",
          `Waiting for ${service} content to load...`
        );
        await ensureContentLoaded(page);
        productJsonResponse = { useHtmlExtraction: true, page: page };
      } else {
        // Blinkit & Bigbasket: Setup response listener
        let responseHandler;
        const jsonCapturePromise = new Promise((resolve) => {
          responseHandler = async (response) => {
            const url = response.url();
            const isBlinkitUrl = service === "blinkit" && url.includes("blinkit.com/v1/layout/search");
            const isBigbasketUrl = service === "bigbasket" && url.includes("bigbasket.com/listing-svc/v2/products");
            
            if (!isBlinkitUrl && !isBigbasketUrl) return;

            if (isBlinkitUrl) {
              console.log(`[debug-ws-response] Found blinkit search URL: ${url}`);
            }

            try {
              const json = await response.json();
              const isBlinkitJson = service === "blinkit" && json && json.response && Array.isArray(json.response.snippets);
              const isBigbasketJson = service === "bigbasket" && json && json.tabs && Array.isArray(json.tabs) && json.tabs[0] && json.tabs[0].product_info;

              if (isBlinkitUrl) {
                console.log(`[debug-ws-response] isBlinkitJson: ${isBlinkitJson}, hasSnippets: ${json && json.response && Array.isArray(json.response.snippets)}`);
              }

              if ((isBlinkitJson || isBigbasketJson) && !url.includes("empty_search")) {
                console.log(`Captured ${service} product JSON from: ${url}`);
                resolve(json);
              }
            } catch (e) {
              if (isBlinkitUrl) {
                console.log(`[debug-ws-response] Error parsing json for blinkit: ${e.message}`);
              }
            }
          };
          page.on("response", responseHandler);
        });

        // Navigate page
        const navigationSuccess = await navigateToSearch(page, searchTerm);
        if (!navigationSuccess) {
          if (page && typeof page.off === "function" && responseHandler) {
            page.off("response", responseHandler);
          }
          updateSearchStatus(
            service,
            "error",
            `Failed to navigate to ${service} search page.`
          );
          return [];
        }

        // Race the JSON capture against a 30s timeout
        const timeoutPromise = new Promise((resolve) => setTimeout(() => resolve({ timeout: true }), 30000));
        const result = await Promise.race([jsonCapturePromise, timeoutPromise]);

        // Cleanup response listener immediately to prevent leaks
        if (page && typeof page.off === "function" && responseHandler) {
          page.off("response", responseHandler);
        }

        if (result && result.timeout) {
          console.warn(`[runServiceSearch] Timeout waiting for ${service} JSON response.`);
          updateSearchStatus(service, "empty", `No products found on ${service} (Timeout).`);
          return [];
        }

        productJsonResponse = result;
      }

        // Extract product information - first try from JSON, fallback to HTML if needed
        updateSearchStatus(
          service,
          "extracting",
          `Extracting ${service} products...`
        );
        try {

        if (
          productJsonResponse &&
          productJsonResponse.useHtmlExtraction
        ) {
          console.log(`Using HTML extraction for ${service}`);
          try {
            const pageTitle = await page.title();
            const pageUrl = page.url();
            console.log(`[debug-fallback] Service: ${service}, URL: ${pageUrl}, Title: ${pageTitle}`);
            if (pageTitle.includes("Cloudflare") || pageTitle.includes("Just a moment")) {
              console.warn(`[debug-fallback] Cloudflare bot detection triggered for ${service}!`);
            }
          } catch (err) {
            console.log(`[debug-fallback] Error getting page info: ${err.message}`);
          }
          updateSearchStatus(
            service,
            "extracting",
            `Extracting ${service} products from HTML...`
          );
        }

        // Pass the response with page object to the extraction function
        if (productJsonResponse && productJsonResponse.useHtmlExtraction) {
          productJsonResponse.page = page;
        }

        const products = await extractProductInformation(
          productJsonResponse
        );

        if (products && products.length > 0) {
          updateSearchStatus(
            service,
            "success",
            `Found ${products.length} products on ${service}.`,
            products
          );
          return products;
        } else {
          updateSearchStatus(
            service,
            "empty",
            `No products found on ${service}.`,
            []
          );
          return [];
        }
      } catch (error) {
        console.error(
          `Error during product extraction for ${service}:`,
          error
        );

        // Final fallback - try direct HTML extraction if everything else failed
        try {
          console.log(
            `Attempting direct HTML extraction for ${service} as final fallback`
          );
          updateSearchStatus(
            service,
            "extracting",
            `Final attempt to extract ${service} products...`
          );

          // Create a simplified wrapper to pass the page
          const htmlProducts = await extractProductInformation({
            useHtmlExtraction: true,
            page: page,
          });

          if (htmlProducts && htmlProducts.length > 0) {
            updateSearchStatus(
              service,
              "success",
              `Found ${htmlProducts.length} products on ${service} via direct HTML extraction.`,
              htmlProducts
            );
            return htmlProducts;
          } else {
            updateSearchStatus(
              service,
              "empty",
              `No products found on ${service}.`,
              []
            );
            return [];
          }
        } catch (fallbackError) {
          console.error(
            `Final extraction attempt failed for ${service}:`,
            fallbackError
          );
          updateSearchStatus(
            service,
            "error",
            `Failed to get product data: ${error.message}`
          );
          return [];
        }
      }
    } catch (error) {
      console.error(`Error in ${service} search:`, error);
      updateSearchStatus(
        service,
        "error",
        `Search error: ${error.message}`
      );
      return [];
    }
  };

  // Start all searches dynamically in parallel
  const searchPromises = SVCS.map((svc) =>
    runServiceSearch(
      svc,
      searchPages[svc],
      serviceHelpers[svc].search.navigateToSearch,
      serviceHelpers[svc].search.ensureContentLoaded,
      serviceHelpers[svc].search.extractProductInformation
    )
  );

  Promise.all(searchPromises)
    .then((resultsArray) => {
      // Combine all search results
      const allProducts = {};
      let totalProducts = 0;
      const productCount = { total: 0 };

      SVCS.forEach((svc, index) => {
        const svcProducts = resultsArray[index];
        allProducts[svc] = svcProducts;
        totalProducts += svcProducts.length;
        productCount[svc] = svcProducts.length;
      });
      productCount.total = totalProducts;

      // Send the combined results to the client
      ws.send(
        JSON.stringify({
          status: "success",
          action: "searchResults",
          products: allProducts,
          productCount: productCount,
          message: `Found ${totalProducts} products across all services.`,
        })
      );

      // Final status update
      ws.send(
        JSON.stringify({
          action: "statusUpdate",
          step: "search",
          status: "completed",
          success: true,
          message: `Search completed for "${searchTerm}".`,
        })
      );
    })
    .catch((error) => {
      console.error("Error in search process:", error);
      ws.send(
        JSON.stringify({
          action: "statusUpdate",
          step: "search",
          status: "error",
          success: false,
          message: `Search error: ${error.message}`,
        })
      );
    });
}

async function handleCloseBrowser(ws, clientId, data) {
  // Close all browser contexts / pages if they exist
  const clientPages = pages.get(clientId);
  if (clientPages) {
    const closePromises = [];

    for (const service of SVCS) {
      const p = clientPages[service];
      if (p) {
        if (p._clientContext) {
          closePromises.push(p._clientContext.close());
        } else {
          closePromises.push(p.close());
        }
      }
    }

    await Promise.all(closePromises);

    browsers.delete(clientId);
    pages.delete(clientId);
    locationSet.delete(clientId);

    ws.send(
      JSON.stringify({
        status: "success",
        action: "close",
        message: "All browser contexts closed successfully.",
      })
    );
  } else {
    ws.send(
      JSON.stringify({
        status: "error",
        action: "close",
        message: "No active browser contexts to close.",
      })
    );
  }
}

const stealthUtils = require("./stealthUtils");

// Browser management functions
async function getGlobalBrowser() {
  if (!globalBrowserPromise) {
    console.log("Launching shared global Puppeteer browser...");
    globalBrowserPromise = puppet.launch({
      headless: "new",
      args: stealthUtils.LAUNCH_ARGS,
      executablePath: process.env.PUPPETEER_EXEC_PATH,
    });
  }
  return globalBrowserPromise;
}

async function initBrowser(cid, svc) {
  try {
    const b = await getGlobalBrowser();
    // Return mock/dummy reference for compatibility with existing client map structure
    if (!browsers.get(cid)) {
      browsers.set(cid, {});
    }
    browsers.get(cid)[svc] = b;
    return b;
  } catch (err) {
    console.error(`Error getting shared browser for ${svc}:`, err);
    throw new Error(`Failed to initialize browser: ${err.message}`);
  }
}

async function getPage(cid, svc, browser) {
  try {
    // Check if page already exists
    if (pages.get(cid)[svc]) {
      return pages.get(cid)[svc];
    }

    // Create page in default browser context to ensure stealth plugin evasions are fully active
    console.log(`Creating page for client ${cid} - ${svc} in default browser context...`);
    const p = await browser.newPage();
    await stealthUtils.applyPageStealthInjections(p);

    // Store page reference
    pages.get(cid)[svc] = p;
    return p;
  } catch (err) {
    console.error(`Error creating page for ${svc}:`, err);
    throw new Error(`Failed to create page: ${err.message}`);
  }
}

async function cleanup(cid) {
  try {
    const clientPages = pages.get(cid);
    if (clientPages) {
      for (const svc of SVCS) {
        const p = clientPages[svc];
        if (p) {
          if (p._clientContext) {
            await p._clientContext.close();
            console.log(`Closed lightweight browser context for ${svc} of client ${cid}`);
          } else {
            await p.close().catch(() => {});
          }
        }
      }
    }

    // Clear all client references
    browsers.delete(cid);
    pages.delete(cid);
    locSet.delete(cid);
  } catch (err) {
    console.error(`Error cleaning up resources for client ${cid}:`, err);
  }
}

const PORT = process.env.PORT || 5000;

app.get("*", (req, res) => {
  if (!req.path.startsWith("/api/")) {
    const publicPath =
      process.env.NODE_ENV === "production" ? "./public" : "../public";
    const indexPath = path.join(__dirname, publicPath, "index.html");

    // Only log in non-production to reduce verbosity
    if (process.env.NODE_ENV !== "production") {
      console.log(`Serving index.html from: ${indexPath}`);
    }

    res.sendFile(indexPath, (err) => {
      if (err) {
        console.error(`Error serving index.html: ${err.message}`);
        res.status(500).send("Error loading the application");
      }
    });
  } else {
    res.status(404).json({ error: "API endpoint not found" });
  }
});

// Start server
srv.listen(PORT, () => {
  console.log(`Server listening on port ${PORT}`);
  console.log(`Available services: ${SVCS.join(", ")}`);
});

// Handle graceful shutdown
process.on("SIGINT", async () => {
  console.log("Shutting down server...");
  
  // Close all active browser contexts
  for (const [cid] of browsers.entries()) {
    await cleanup(cid);
  }

  // Close the global browser
  if (globalBrowserPromise) {
    try {
      const browser = await globalBrowserPromise;
      await browser.close();
      console.log("Closed global shared browser instance.");
    } catch (err) {
      console.error("Error closing global shared browser:", err);
    }
  }
  
  // Close server
  srv.close(() => {
    console.log("Server shutdown complete");
    process.exit(0);
  });
});
