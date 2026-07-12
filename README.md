# QuickCom Scraper

QuickCom is a web application that helps you find and compare product prices across Blinkit, Bigbasket, JioMart, and Zepto. Instead of checking each app individually, you can search once and see all the options, saving you time and money when ordering groceries or essentials.

## Supported Platforms

| Platform | Status |
|----------|--------|
| ✅ Blinkit | Working — 24+ products with complete data (prices, discounts, quantities) |
| ✅ Bigbasket | Working — CDP stealth injection bypasses Akamai detection |
| ✅ JioMart | Working — 50+ products with complete data |
| ✅ Zepto | Working — CDP stealth injection bypasses bot detection |
| ❌ Instamart (Swiggy) | Blocked by AWS WAF challenge.js — requires Go awswaf solver |

## Demo

![Location and Search Interface](./screenshots/quickcom-search-interface.png)
![Product Results](./screenshots/quickcom-results.png)

## Features

- **Multi-platform Search**: Find products across 4 platforms with one search
- **Location-based Results**: Set your location once to get accurate delivery options
- **Real-time Comparison**: See prices and delivery times side by side
- **Visual Indicators**: Easily spot discounts and best deals
- **Responsive Design**: Works well on both desktop and mobile
- **Live Updates**: Results appear as they're found
- **Complete Product Info**: See quantity, price, discounts, and delivery times
- **Stealth Anti-Detection**: CDP-level stealth injection bypasses Akamai and bot detection

## Technology Stack

### Backend
- **Python 3.14** — Programming language
- **Zendriver** — Browser automation with CDP stealth injection
- **Playwright** — Web automation engine (underlying Zendriver)

### Frontend
- **Streamlit** — UI framework
- **websocket-client** — Communication library

## Project Structure

```
QuickCom/
├── backend_py/                # Python backend
│   ├── scrapers/              # Individual store scrapers
│   │   ├── blinkit.py         # Blinkit scraper (CDP API interception)
│   │   ├── bigbasket.py       # Bigbasket scraper (cookie location + DOM extraction)
│   │   ├── jiomart.py         # JioMart scraper (HTML extraction)
│   │   └── zepto.py           # Zepto scraper (data-slot-id extraction)
│   ├── awswaf/                # AWS WAF challenge solver (for future use)
│   │   ├── aws.py             # WAF solver main class
│   │   ├── verify.py          # Challenge verification (sha256, scrypt, network_bandwidth)
│   │   ├── fingerprint.py     # Browser fingerprint generation
│   │   └── crypto.py          # Encryption utilities
│   └── __init__.py
├── streamlit/                 # Streamlit Frontend
│   └── app.py                 # Main UI application
├── requirements.txt           # Python Dependencies
└── README.md                  # This documentation
```

## Installation

### Prerequisites
- Python 3.14+
- Chrome/Chromium browser (for Zendriver automation)

### Setup

1. **Clone the Repository:**
```shell
git clone https://github.com/yourusername/QuickCom.git
cd QuickCom
```

2. **Install Dependencies:**
```shell
pip install -r requirements.txt
playwright install chromium
```

### Running the Application

```shell
streamlit run streamlit/app.py
```
The frontend will run on `http://localhost:8501`

## How It Works

Each scraper uses **Zendriver** (a modern headless browser automation library) to:
1. Set location via CDP cookie injection (no UI interaction needed for most sites)
2. Navigate to the search page
3. Extract product data from the rendered DOM or intercepted API responses
4. Structure and return product information

### Anti-Detection

The app uses **CDP-level stealth injection** via `Page.addScriptToEvaluateOnNewDocument` to:
- Hide `navigator.webdriver` flag
- Spoof `navigator.plugins` and `navigator.languages`
- Set realistic `navigator.hardwareConcurrency`
- Configure custom user agent and WebRTC disabling

This bypasses Akamai and standard bot detection systems used by Bigbasket and Zepto.

### AWS WAF Solver

The `backend_py/awswaf/` module can solve AWS WAF challenges programmatically:
- Supports sha256 proof-of-work, scrypt, and network_bandwidth challenge types
- Generates valid `aws-waf-token` values
- Token authentication requires the Go `tls-client` library for perfect TLS fingerprinting

## License

This project is licensed under the MIT License - see the LICENSE file for details.

---

Happy shopping and happy scraping! 🚀
