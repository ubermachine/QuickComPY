# QuickCom Scraper

QuickCom is a highly optimized, asynchronous web application that aggregates product prices across **Blinkit, BigBasket, JioMart, Zepto, and Swiggy Instamart**. It allows you to search across all five major Indian quick commerce platforms simultaneously to compare prices, discounts, and delivery times in a single unified interface.

## Supported Platforms

All five platforms are read by intercepting the private JSON API behind each
site's product grid, never by parsing rendered HTML. The browser negotiates any
WAF challenge natively as it loads the page; we just read the payload it gets back.

| Platform | Status | Intercepted endpoint | Location mechanism |
|----------|--------|----------------------|--------------------|
| ✅ **Blinkit** | Working | `/v1/layout/search` | `gr_1_lat` / `gr_1_lon` cookies |
| ✅ **Swiggy Instamart** | Working | `/api/instamart/search/v2` | Geolocation override + `userLocation` cookie ⚠️ |
| ✅ **Zepto** | Working | `/api/v3/search` | `latitude` / `longitude` / `location` cookies |
| ✅ **BigBasket** | Working | `/listing-svc/v2/products` | `bb_pincode` cookie family |
| ✅ **JioMart** | Working | `/ext/vertex/application/api` | Pincode entered through the site's modal |

> ⚠️ **Instamart location caveat.** Swiggy binds its dark store through an opaque
> `matcher` header derived from the SPA's own state — its search request carries an
> empty `storeId`, and it ignores any location keys written into `localStorage`.
> We override the browser's geolocation and set the cookie Swiggy's own picker
> writes, but results are not guaranteed to be pincode-exact. Prices and products
> are real; the serving store may not be the nearest one.

## Features

- **Multi-platform Search**: Find products across 5 platforms with one search.
- **Location-based Results**: Initialize your location using Pincodes or City names to get accurate, localized delivery options.
- **Bypass WAFs & Bot Detection**: Uses Zendriver with stealth CDP injection to bypass Akamai and AWS WAF challenges natively. API interception completely bypasses HTML scraping traps.
- **Honest failure reporting**: Every platform returns a `status` alongside its
  products, so an empty column says *why* it is empty — `blocked` (bot
  challenge), `timeout`, `error`, or a genuine `empty`. Silent zero-result
  columns were the single hardest thing to debug before this.
- **Retries and early exit**: A missed interception is retried once; a
  confirmed block or a genuinely empty result is not, so a no-match query
  settles in seconds instead of burning two full timeouts.
- **Relevance ranking**: Platforms inject sponsored cards at position 0
  (Blinkit will lead a "milk" search with cake rusk). Results are re-ranked so
  on-topic items surface first — demoted, never dropped, since "curd"
  legitimately returns "Dahi" with no lexical overlap.
- **Asynchronous & Concurrent**: Uses `asyncio.gather()` to fetch data from all 5 platforms simultaneously, typically in 8-12 seconds.
- **Memory Optimized**: Runs a single global Chromium browser instance via FastAPI Lifespan events. Memory footprint fits within a 512MB RAM constraint for free-tier deployments.
- **Modern Glassmorphism UI**: Beautiful, responsive Vanilla HTML/CSS interface with visual badges and dynamic grid layouts.

## Technology Stack

### Backend
- **Python 3.11+**
- **FastAPI** — High-performance async API framework
- **Uvicorn** — ASGI web server
- **Zendriver** — Headless browser automation (Playwright wrapper) with advanced stealth

### Frontend
- **Vanilla HTML/CSS/JS** — Lightweight, no-build-step frontend
- **Inter Font & Custom Gradients** — Premium UI feel

### Deployment
- **Docker** — Optimized `python:3.11-slim` multi-stage image.
- **Render / Google Cloud Run** — Configuration files included for easy serverless deployment.

## API

| Endpoint | Purpose |
|----------|---------|
| `GET /api/services` | Platform registry (key, label, brand colours). The frontend reads this instead of hardcoding the list. |
| `POST /api/set-location` | `{"location": "201306"}` — warms a session per platform. Returns `{platform: bool}`. |
| `GET /api/search?q=` | Returns `{platform: {products, status, message}}` for every platform. |

`status` is one of `ok`, `empty`, `blocked`, `timeout`, `error`.

### Adding a platform

1. Write `backend_py/scrapers/<name>.py` with `set_location(page, location)` and
   `search(page, term)`. Build `search` on `common.intercept_json` +
   `common.run_search` — they handle interception, retries, block detection and
   ranking, so a new scraper is a URL matcher plus a payload parser.
2. Add one `Platform(...)` row to `backend_py/registry.py`.

That is the whole change: `main.py` and the frontend both read the registry.

### Tuning

| Env var | Default | Purpose |
|---------|---------|---------|
| `MAX_CONCURRENT_TABS` | `4` | Chromium tabs open at once. Lower it on a 512MB box. |
| `SEARCH_TIMEOUT` | `60` | Per-platform search ceiling, seconds. |
| `LOCATION_TIMEOUT` | `25` | Per-platform location ceiling, seconds. |

## Project Structure

```
QuickCom/
├── backend_py/                # Backend logic
│   ├── registry.py            # Platform list — single source of truth
│   └── scrapers/              # Individual store scrapers
│       ├── common.py          # Shared interception, retries, ranking
│       ├── blinkit.py         
│       ├── bigbasket.py       
│       ├── jiomart.py         
│       ├── zepto.py           
│       └── instamart.py       
├── static/                    # Frontend assets
│   └── index.html             # Main Single Page Application
├── main.py                    # FastAPI server & routes
├── Dockerfile                 # Optimized slim Docker image
├── render.yaml                # Render Blueprint deployment config
├── requirements.txt           # Python Dependencies
└── README.md                  # Documentation
```

## Installation & Setup

### Prerequisites
- Python 3.11 or higher
- Google Chrome or Chromium installed on your system

### Local Development

1. **Clone the Repository:**
```shell
git clone https://github.com/ubermachine/QuickComPY.git
cd QuickComPY
```

2. **Install Dependencies:**
```shell
pip install -r requirements.txt
playwright install chromium
```

3. **Run the Server:**
```shell
python main.py
```
*Note: The app runs via Uvicorn programmatically on `http://localhost:8000`.*

## Deployment

The application is heavily optimized for low-memory environments (like Render's Free Tier or Google Cloud Run).

### Google Cloud Run
You can easily deploy this container to Google Cloud Run:
```shell
gcloud run deploy quickcom \
  --source . \
  --allow-unauthenticated \
  --memory 1Gi \
  --region us-central1
```

### Render
The repository includes a `render.yaml` Blueprint. Simply connect your GitHub repository to Render and it will automatically provision the Docker-based Web Service using the specified port and commands.

## Architecture Highlights

- **API Interception > HTML Scraping**: Platforms like Swiggy and Zepto heavily obfuscate their HTML and use AWS WAF. QuickCom attaches `page.on('response')` CDP listeners to intercept the clean JSON payloads from internal APIs, bypassing DOM instability.
- **Single Browser Instance**: Instead of opening and closing browsers per request, `main.py` initializes a single global Zendriver instance that lives for the lifetime of the FastAPI app, drastically reducing latency and memory overhead.
- **Stealth Initialization**: Locations are injected directly into `localStorage`, `sessionStorage`, and CDP Cookies via headless scripts, avoiding fragile UI interactions like clicking "Change Location" modals.

## License
MIT License
