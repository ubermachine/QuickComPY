# QuickCom Scraper

QuickCom is a highly optimized, asynchronous web application that aggregates product prices across **Blinkit, BigBasket, JioMart, Zepto, and Swiggy Instamart**. It allows you to search across all five major Indian quick commerce platforms simultaneously to compare prices, discounts, and delivery times in a single unified interface.

## Supported Platforms

| Platform | Status | Extraction Method |
|----------|--------|-------------------|
| ✅ **Blinkit** | Working | API Interception (`/v6/search/products`) |
| ✅ **Swiggy Instamart**| Working | API Interception (`/api/instamart/search/v2`) |
| ✅ **Zepto** | Working | API Interception (`/api/v3/search`) |
| ✅ **BigBasket** | Working | HTML Parsing (`bb-product-card`) |
| ✅ **JioMart** | Working | HTML Parsing (`aisle-product-card`) |

## Features

- **Multi-platform Search**: Find products across 5 platforms with one search.
- **Location-based Results**: Initialize your location using Pincodes or City names to get accurate, localized delivery options.
- **Bypass WAFs & Bot Detection**: Uses Zendriver with stealth CDP injection to bypass Akamai and AWS WAF challenges natively. API interception completely bypasses HTML scraping traps.
- **Asynchronous & Concurrent**: Uses `asyncio.gather()` to fetch data from all 5 platforms simultaneously within 10-15 seconds.
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

## Project Structure

```
QuickCom/
├── backend_py/                # Backend logic
│   └── scrapers/              # Individual store scrapers
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
