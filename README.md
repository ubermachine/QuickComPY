# QuickCom Scraper

QuickCom is a highly optimized, asynchronous web application that aggregates product prices across **Blinkit, BigBasket, JioMart, Zepto, Swiggy Instamart and Amazon.in**. It allows you to search across six Indian commerce platforms simultaneously to compare prices, discounts, and delivery times in a single unified interface.

## Supported Platforms

The five quick-commerce platforms are read by intercepting the private JSON API
behind each site's product grid, never by parsing rendered HTML. The browser
negotiates any WAF challenge natively as it loads the page; we just read the
payload it gets back. Amazon is the exception — it renders results server-side,
so it is read from the DOM.

| Platform | Status | Intercepted endpoint | Location mechanism |
|----------|--------|----------------------|--------------------|
| ✅ **Blinkit** | Working | `/v1/layout/search` | `gr_1_lat` / `gr_1_lon` cookies |
| ✅ **Swiggy Instamart** | Working | `/api/instamart/search/v2` | Geolocation override + `userLocation` cookie ⚠️ |
| ✅ **Zepto** | Working | `/api/v3/search` | `latitude` / `longitude` / `location` cookies |
| ✅ **BigBasket** | Working | `/listing-svc/v2/products` | `bb_pincode` cookie family |
| ✅ **JioMart** | Working | `/ext/vertex/application/api` | `app_location_details` / `app_geolocation` cookies — verified against the header |
| ✅ **Amazon.in** | Working | DOM (`[data-component-type="s-search-result"]`) | `glow/address-change` — verified against the city Amazon returns |

### JioMart location

JioMart's location modal is a Google Places autocomplete whose suggestion list
does not lay out in headless Chrome — its `.pac-item` reports a zero-size
bounding box, so neither synthetic nor real CDP clicks can pick a result. An
earlier implementation drove that modal, slept seven seconds through it, and
returned `True` regardless, leaving every user on JioMart's **Mumbai** default
no matter which pincode they entered.

Location is now set through the same cookies the site writes itself
(`app_location_details`, `app_geolocation`, plus the `pin` localStorage key),
and confirmed by reading the pincode back out of JioMart's own header. That is
both correct and roughly twice as fast.

### Amazon.in notes

Amazon is a general marketplace, not a grocer, which needs two adjustments the
other five do not:

- **Searches are scoped to the grocery index** (`&i=grocery`). Unscoped, a search
  for "milk" returns the 2009 film and an MP3 album alongside actual milk. If the
  grocery index has no matches the search widens to all departments rather than
  returning an empty column.
- **Sponsored cards are dropped, not just demoted**, whenever organic results
  exist. On a quick-commerce grid a paid placement is usually still a groceries
  item; on Amazon it is frequently a different category altogether. If every
  result is sponsored they are kept, since a paid placement beats a blank column.

Product titles come from the thumbnail's `alt` text — Amazon's `h2` holds only
the brand — and the MRP is read from the element explicitly marked
`data-a-strike`, because the looser `.a-text-price` selector also matches
per-unit prices (it will hand you ₹60 for a ₹360 item).

Amazon's delivery pincode is genuinely settable: `set_location` posts to the
endpoint behind the "Deliver to" control and returns `True` only when Amazon
confirms the change, reporting the city it resolved to.

> ⚠️ **Instamart location caveat.** Swiggy binds its dark store through an opaque
> `matcher` header derived from the SPA's own state — its search request carries an
> empty `storeId`, and it ignores any location keys written into `localStorage`.
> We override the browser's geolocation and set the cookie Swiggy's own picker
> writes, but results are not guaranteed to be pincode-exact. Prices and products
> are real; the serving store may not be the nearest one.

## Features

- **Multi-platform Search**: Find products across 6 platforms with one search.
- **Location-based Results**: Initialize your location using Pincodes or City names to get accurate, localized delivery options.
- **Bypass WAFs & Bot Detection**: Uses Zendriver with stealth CDP injection to bypass Akamai and AWS WAF challenges natively. API interception completely bypasses HTML scraping traps.
- **Honest failure reporting**: Every platform returns a `status` alongside its
  products, so an empty column says *why* it is empty — `blocked` (bot
  challenge), `timeout`, `error`, or a genuine `empty`. Silent zero-result
  columns were the single hardest thing to debug before this.
- **Retries and early exit**: A missed interception is retried once; a
  confirmed block or a genuinely empty result is not, so a no-match query
  settles in seconds instead of burning two full timeouts.
- **Sort and filter by discount**: Every product carries a numeric
  `discountPercent`, computed from price against MRP rather than trusted from
  the platform's own copy (which ranges from `SAVE 15%` to `₹16 OFF` to an
  unrelated promo). Results can be ordered by biggest saving or filtered to a
  minimum discount, without changing the default search.
- **Wider candidate pool**: Scrapers keep `POOL_SIZE` (40) ranked candidates
  while the UI shows `MAX_PRODUCTS` (8). Sorting by discount therefore reaches
  genuine bargains that rank tenth or lower on relevance -- trimming to eight
  before sorting would hide them permanently.
- **No redundant warmups**: `search` used to load each platform's homepage
  before the search URL, to establish session and WAF cookies. Those cookies
  live in the browser profile, so once `set_location` has visited an origin the
  extra load is pure latency — measured at 3.3s per Instamart search. The
  warmup now runs only when the origin genuinely has no cookies yet, falling
  back to warming up whenever that cannot be determined.
- **Waiting on conditions, not clocks**: fixed `sleep()` calls were replaced by
  polling for the thing actually being awaited. The DOM scraper waits for the
  product count to *stabilise* rather than for the first card — Amazon streams
  its grid in, and reading on first sight captured four products out of forty.
- **Short-lived result cache**: Re-sorting or re-filtering reuses the scraped
  pool for `SEARCH_CACHE_TTL` seconds (default 120) instead of hitting all six
  platforms again -- a re-sort drops from ~17s to under 0.1s, and it removes
  the repeat traffic that invites bot challenges. Cleared whenever the location
  changes, since cached pools are location-specific.
- **Relevance ranking**: Platforms inject sponsored cards at position 0
  (Blinkit will lead a "milk" search with cake rusk). Results are re-ranked so
  on-topic items surface first — demoted, never dropped, since "curd"
  legitimately returns "Dahi" with no lexical overlap.
- **Streamed results**: `/api/search/stream` sends each platform's column as
  Server-Sent Events the moment that platform lands, so the page fills in
  progressively instead of showing nothing until the slowest of six finishes.
  The slowest platform is routinely three times the fastest, and under the
  batch endpoint every user paid that worst case. `/api/search` is unchanged
  for callers that want one JSON body.
- **Pooled browser tabs**: A tab is not free — a new target costs a renderer
  spin-up plus the CDP round trips to install the stealth script, enable
  Network and push the resource blocklist, and that was paid and thrown away
  six times per search. Tabs are now leased from a pool, blanked on release
  (which drops the site's DOM and JS heap) and reused. The pool's size is also
  the concurrency cap, so there is no separate semaphore to keep in step with
  it, and tabs idle for `TAB_IDLE_TTL` are closed so a quiet box drifts back
  down to the browser alone. Worth keeping the size of this in proportion:
  building a tab measured at a median of 33ms against a warm local browser, so
  the saving is around 200ms on a six-platform search — real, but a rounding
  error next to the scrape itself. The streaming endpoint and the local
  re-sorting below are where the time actually goes.
- **One scrape per question**: Identical queries arriving together collapse
  onto a single in-flight scrape rather than each starting their own round of
  traffic at the platforms. A client that hangs up does not cancel the scrape
  others are waiting on, and the result is still cached for the next caller.
- **Sorting and filtering without a request**: Each platform's full ranked pool
  is sent alongside the visible page of it, so changing sort order or minimum
  discount is a re-render of data already in the browser — no round trip, no
  spinner, no server-side re-sort. gzip makes the extra payload cheaper than
  the request it removes.
- **Asynchronous & Concurrent**: Every platform is scraped at once, bounded by
  `MAX_CONCURRENT_TABS`; typically 12-16 seconds for all six to finish, though
  with the streaming endpoint the first column lands in a small fraction of that.
- **Memory Optimized**: Runs a single global Chromium browser instance via FastAPI Lifespan events.
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
| `GET /api/services` | Platform registry (key, label, brand colours) plus `maxProducts`. The frontend reads this instead of hardcoding the list. |
| `POST /api/set-location` | `{"location": "201306"}` — warms a session per platform. Returns `{platform: bool}`. |
| `GET /api/search?q=` | Returns `{platform: {products, pool, status, message, matched}}` for every platform, once all six have landed. |
| `GET /api/search/stream?q=` | The same search as Server-Sent Events: one `result` event per platform as it lands, carrying that platform's object plus its `service` key, then a final `done`. |

Both search endpoints accept the same two optional view parameters. Both
default to the original behaviour, so an unchanged call returns exactly what it
always did:

| Param | Default | Meaning |
|-------|---------|---------|
| `sort` | `relevance` | `relevance` keeps the ranking; `discount` orders biggest saving first. |
| `min_discount` | `0` | Drop anything discounted less than this percentage (0-99). |

`matched` reports how many of a platform's candidates passed the filter, so the
UI can say "showing top 8 of 23" rather than implying there were only eight.

`products` is the visible page; `pool` is every ranked candidate behind it, sent
so the browser can re-sort and re-filter locally rather than asking again. The
two overlap, but the overlap is identical text and gzip charges almost nothing
for it — far less than a round trip per dropdown change.

`status` is one of `ok`, `empty`, `blocked`, `timeout`, `error`.

### Adding a platform

1. Write `backend_py/scrapers/<name>.py` with `set_location(page, location)` and
   `search(page, term)`. Build `search` on `common.run_search` plus either
   `common.intercept_json` (sites that call a private JSON API) or
   `common.scrape_dom` (server-rendered HTML, as Amazon does). They handle
   retries, block detection, dedupe, ranking and the 8-item cap, so a new
   scraper is a URL matcher plus a payload parser.
2. Add one `Platform(...)` row to `backend_py/registry.py`.

That is the whole change: `main.py` and the frontend both read the registry.

### Tuning

| Env var | Default | Purpose |
|---------|---------|---------|
| `MAX_CONCURRENT_TABS` | `4` | Chromium tabs open at once — the main memory lever, see below. |
| `BLOCK_ASSETS` | `1` | Skip fetching images/fonts/media/telemetry. `0` to fetch everything. |
| `SEARCH_TIMEOUT` | `60` | Per-platform search ceiling, seconds. |
| `LOCATION_TIMEOUT` | `25` | Per-platform location ceiling, seconds. |
| `SEARCH_CACHE_TTL` | `120` | Seconds a scraped pool is reused for re-sorting. `0` disables. |
| `TAB_IDLE_TTL` | `300` | Seconds an unused pooled tab is kept warm before being closed. |

## Memory

Measured on a six-platform search, sampling Chromium plus Python RSS for the
duration rather than reading it once at the end:

| `MAX_CONCURRENT_TABS` | Peak RSS | Search wall time |
|---|---|---|
| 2 | ~1.6 GB | 13-15s |
| 4 (default) | ~2.3 GB | ~10.5s |
| 6 | ~2.1 GB | ~14.6s |

Peak tracks the number of concurrent renderer processes, not page weight. Going
to 6 is worse on both axes on a machine this size — the extra parallelism costs
more in contention than it saves in waiting.

**These numbers predate the current browser flags** and have not been re-measured
since. Chromium is now launched with site isolation and the back/forward cache
off (`--disable-features=site-per-process,IsolateOrigins,BackForwardCache`) and,
when `BLOCK_ASSETS` is on, with images disabled in Blink itself rather than only
blocked at the network layer. Since the table's own finding is that peak tracks
*renderer process count*, and site isolation is what multiplies that count per
origin, the flags should move peak down — but treat that as a prediction until
someone re-runs the measurement on a real box. The tab pool cuts the other way
by a smaller amount: up to `MAX_CONCURRENT_TABS` tabs now persist between
searches, though blanked to `about:blank` and closed after `TAB_IDLE_TTL`.

Chromium is also told not to throttle background tabs
(`--disable-background-timer-throttling`, `--disable-backgrounding-occluded-windows`,
`--disable-renderer-backgrounding`). Every tab we drive is a background tab, so
left on, that throttling slows exactly the concurrent scrapes the pool exists to
run.

**This does not fit a 512MB host, and cannot be made to.** Chromium's per-renderer
floor is the constraint, so the knob moves peak between roughly 1.6GB and 2.3GB
and no further. Anything advertising a 512MB free tier (Render, Koyeb) is out;
see the hosting notes in the repository discussion for what works.

`BLOCK_ASSETS` stops the browser fetching images, fonts, media and third-party
telemetry — none of which any scraper reads, since image *URLs* come from the
JSON payloads and DOM attributes rather than the decoded pixels. Worth being
straight about the result: it did **not** measurably reduce peak memory
(1942MB vs 1936MB), because renderer process overhead dominates. It is kept on
by default because it removes a large number of pointless requests per search,
which is worth having on a metered or rate-limited host, and it is one flag to
turn off if a platform ever needs its images.

## Project Structure

```
QuickCom/
├── backend_py/                # Backend logic
│   ├── registry.py            # Platform list — single source of truth
│   └── scrapers/              # Individual store scrapers
│       ├── common.py          # Shared interception/DOM, retries, ranking
│       ├── amazon.py          # DOM scraper (server-rendered)
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
├── requirements.txt           # Runtime dependencies (what the image installs)
├── requirements-dev.txt       # Test and debugging tools, not shipped
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
pip install -r requirements.txt        # to run the app
pip install -r requirements-dev.txt    # to run the tests as well
```
`requirements.txt` is runtime-only, so the production image does not carry
pytest, httpx or beautifulsoup4. Chromium must be on the system; set
`CHROME_PATH` if it is somewhere zendriver will not find it.

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
- **Pooled, blanked tabs**: Tabs are leased from a fixed pool rather than
  created per platform per search. Release clears the tab's CDP handlers before
  returning it — under pooling a scraper that died mid-interception would
  otherwise leak its callbacks into whichever platform borrowed the tab next,
  which is a correctness bug and not merely a leak.
- **Stealth Initialization**: Locations are injected directly into `localStorage`, `sessionStorage`, and CDP Cookies via headless scripts, avoiding fragile UI interactions like clicking "Change Location" modals.

## License
MIT License
