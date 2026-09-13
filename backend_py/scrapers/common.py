"""Shared scraping primitives.

The five quick-commerce platforms all render their product grid from a private
JSON API, so each scraper does the same thing: warm up a session on the origin,
navigate to the search URL, intercept the API response over CDP, and parse it.
`intercept_json` holds that once. Amazon renders server-side instead, so
`scrape_dom` is its counterpart -- same block detection, same ScrapeResult
contract, so callers cannot tell the two apart.

Both feed `run_search`, which adds what the per-platform copies were each
missing: retrying the response-body fetch, telling "blocked" apart from "no
results", and pushing sponsored/irrelevant cards below real matches.
"""

import asyncio
import json
import re
import unicodedata

import zendriver as zd

# Status values returned alongside products. The frontend renders each
# differently -- an empty list means something very different when the platform
# served us a bot challenge than when the query genuinely has no matches.
OK = "ok"
EMPTY = "empty"
BLOCKED = "blocked"
TIMEOUT = "timeout"
ERROR = "error"

MAX_PRODUCTS = 8

# How many ranked candidates each scraper keeps behind the visible MAX_PRODUCTS.
# Sorting or filtering by discount has to see past the eight most *relevant*
# items, or a 60%-off product sitting tenth by relevance could never surface.
POOL_SIZE = 40

# Sort modes accepted by the search API.
SORT_RELEVANCE = "relevance"
SORT_DISCOUNT = "discount"
SORT_MODES = (SORT_RELEVANCE, SORT_DISCOUNT)

# How long to keep listening after an API response that contained no products,
# in case the grid arrives in a follow-up paginated call.
EMPTY_GRACE = 2.5

# Phrases that appear on a real bot-challenge interstitial. Matched against the
# page's *visible text and title* rather than its raw HTML: scanning raw HTML is
# how an earlier version reported every Swiggy page as blocked, because Swiggy
# embeds the AWS WAF SDK (edge.sdk.awswaf.com/challenge.js) on healthy pages too.
_BLOCK_PHRASES = (
    "are you a human",
    "access denied",
    "request blocked",
    "attention required",
    "unusual traffic",
    "verify you are a human",
    "enter the characters you see below",
    "please enable javascript and cookies",
    "checking your browser",
    "robot check",
)

# A challenge page is a stub. Anything with a real app shell rendered is not one,
# however many WAF scripts it happens to load.
_BLOCK_TEXT_CEILING = 2000

# Live challenge widgets. Presence of the *container* means a challenge is being
# shown; the vendor SDK merely being loaded means nothing.
_BLOCK_SELECTORS = (
    "#challenge-running",
    "#challenge-form",
    "form[action*='validateCaptcha']",
    "#captchacharacters",
    "[id*='awswaf-captcha']",
    "iframe[src*='awswaf.com/captcha']",
    "#px-captcha",
)

# HTTP statuses that mean the origin rejected us rather than the page failing.
_BLOCK_STATUSES = (401, 403, 405, 429, 503)


class ScrapeResult:
    """Products plus why the list is the length it is."""

    __slots__ = ("products", "status", "message")

    def __init__(self, products=None, status=OK, message=None):
        self.products = products or []
        self.status = status
        self.message = message

    def to_dict(self):
        return {
            "products": self.products,
            "status": self.status,
            "message": self.message,
        }

    def __repr__(self):
        return f"<ScrapeResult {self.status} n={len(self.products)}>"


# --------------------------------------------------------------------------
# Relevance
# --------------------------------------------------------------------------

_TOKEN_RE = re.compile(r"[a-z0-9]+")

# Query words that carry no signal for matching a product title.
_STOPWORDS = {"the", "and", "for", "with", "pack", "of", "ml", "kg", "gm", "g", "l"}


def _tokens(text):
    return [
        t
        for t in _TOKEN_RE.findall((text or "").lower())
        if len(t) >= 3 and t not in _STOPWORDS
    ]


def _score_tokens(name, query_tokens):
    """`relevance_score` with the query already tokenised.

    Split out because ranking scores a forty-product pool against one query:
    tokenising that query per product meant running the token regex and the
    stopword filter forty times over for an identical answer. Indexing the name
    once replaces the linear `list.index` scan the per-token loop was doing.
    """
    if not query_tokens:
        return 0.0
    name_tokens = _tokens(name)
    if not name_tokens:
        return 0.0
    # First occurrence per token, which is exactly what `.index()` returned.
    first_at = {}
    for i, t in enumerate(name_tokens):
        if t not in first_at:
            first_at[t] = i
    haystack = (name or "").lower()

    score = 0.0
    for t in query_tokens:
        idx = first_at.get(t)
        if idx is not None:
            score += 1.0
            score += 0.5 * (1.0 - idx / len(name_tokens))
        elif t in haystack:
            score += 0.5
    if score == 0.0:
        return 0.0

    # Length penalty, capped so a very long title cannot go negative and end up
    # below a genuine non-match.
    return score - min(len(name_tokens), 20) * 0.02


def relevance_score(name, query):
    """Score how well a product name answers the query.

    Counting bare token hits is not enough: searching "butter" on Instamart
    returns "Amul Unsalted Butter" and "Plum Vanilla Caramello Body Lotion |
    Cocoa Butter & Vitamin B5", and both contain the word once. Three signals
    separate them --

      * a whole-word hit beats a substring hit (plurals, compounds),
      * an early hit beats one buried at the end of a marketing title,
      * a concise title beats a long one that merely mentions the term.

    Used to demote, never to drop: "curd" legitimately returns "Amul Masti
    Dahi" with no lexical overlap at all, and discarding that would be worse
    than ranking it low.
    """
    return _score_tokens(name, _tokens(query))


def rank_by_relevance(products, query):
    """Stable-sort products so on-topic items outrank sponsored filler.

    Platforms inject ads at position 0 (Blinkit will happily lead a "milk"
    search with cake rusk). Sorting is stable, so within one score band the
    platform's own ordering survives.
    """
    if not products:
        return products
    query_tokens = _tokens(query)
    scored = [(_score_tokens(p.get("name"), query_tokens), i, p)
              for i, p in enumerate(products)]
    # If nothing matches textually the query is probably a synonym; leave as-is.
    if all(s == 0.0 for s, _, _ in scored):
        return products
    scored.sort(key=lambda t: (-t[0], t[1]))
    return [p for _, _, p in scored]


# --------------------------------------------------------------------------
# Formatting helpers
# --------------------------------------------------------------------------

RUPEE = "₹"


def _to_float(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    m = re.search(r"\d+(?:\.\d+)?", str(value).replace(",", ""))
    return float(m.group(0)) if m else None


def money(value):
    """Format a number (or a string containing one) as a rupee amount."""
    f = _to_float(value)
    if f is None:
        return None
    return f"{RUPEE}{int(f)}" if f == int(f) else f"{RUPEE}{f:.2f}"


def price_fields(selling, mrp):
    """Derive the price / originalPrice / savings / discount quartet.

    Every platform gives us a selling price and an MRP in some shape; this
    keeps the derived fields consistent so the UI can compare across sources.
    """
    sp = _to_float(selling)
    mp = _to_float(mrp)
    price = money(sp) or "N/A"
    if sp is None or mp is None or mp <= sp:
        return price, None, None, None
    savings = money(mp - sp)
    discount = f"{int(round((mp - sp) / mp * 100))}% OFF"
    return price, money(mp), savings, discount


def clean(text):
    """Collapse whitespace and drop empty strings to None."""
    if not text:
        return None
    text = unicodedata.normalize("NFKC", str(text))
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


# Platform discount copy: "47% OFF", "SAVE 15%", "11% OFF".
_PERCENT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%")


def discount_percent(product):
    """How much a product is discounted, as a number between 0 and 100.

    Derived from price against originalPrice wherever both are known, because
    that is arithmetic rather than trust: platforms write their own discount
    copy and it is inconsistent ("SAVE 15%", "47% OFF", sometimes a rupee
    amount, sometimes an unrelated promo). The copy is only parsed as a
    fallback, for platforms that advertise a percentage without exposing MRP.
    """
    sp = _to_float(product.get("price"))
    mrp = _to_float(product.get("originalPrice"))
    if sp is not None and mrp is not None and mrp > sp > 0:
        return round((mrp - sp) / mrp * 100, 1)

    m = _PERCENT_RE.search(str(product.get("discount") or ""))
    if m:
        try:
            pct = float(m.group(1))
        except ValueError:
            return 0.0
        # Guard against a promo string that is not really a discount.
        return round(pct, 1) if 0 < pct < 100 else 0.0
    return 0.0


def annotate_discounts(products):
    """Attach a numeric discountPercent to every product, in place."""
    for p in products:
        p["discountPercent"] = discount_percent(p)
    return products


def apply_view(products, *, sort=SORT_RELEVANCE, min_discount=0, limit=MAX_PRODUCTS):
    """Filter and order an already-ranked pool for display.

    Kept separate from scraping so the same pool can be re-sorted without
    hitting the platforms again. Input order is the relevance ranking, so
    SORT_RELEVANCE is simply "leave it alone".
    """
    view = list(products)

    if min_discount and min_discount > 0:
        view = [p for p in view if p.get("discountPercent", 0) >= min_discount]

    if sort == SORT_DISCOUNT:
        # Stable, so equally-discounted items keep their relevance order.
        view.sort(key=lambda p: p.get("discountPercent", 0), reverse=True)

    return view[:limit] if limit else view


def dedupe(products):
    """Drop repeat entries, keyed on id then name."""
    seen = set()
    out = []
    for p in products:
        key = p.get("id") or p.get("name")
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out


# --------------------------------------------------------------------------
# Interception engine
# --------------------------------------------------------------------------

_BLOCK_PROBE_JS = """
JSON.stringify((function () {
  var sels = %s;
  var widget = null;
  for (var i = 0; i < sels.length; i++) {
    var el = document.querySelector(sels[i]);
    // A hidden node proves nothing -- the challenge must actually be showing.
    if (el && el.offsetParent !== null) { widget = sels[i]; break; }
  }
  var body = document.body ? (document.body.innerText || '') : '';
  return {
    widget: widget,
    title: (document.title || '').slice(0, 200),
    text: body.slice(0, 4000),
    length: body.length
  };
})())
"""

# Interpolated once at import: the selector list never changes, and json.dumps
# of it was being redone on every probe.
_BLOCK_PROBE = _BLOCK_PROBE_JS % json.dumps(list(_BLOCK_SELECTORS))


async def _page_looks_blocked(page):
    """True when the current document is a bot challenge rather than the site.

    Deliberately conservative. A false positive is expensive: BLOCKED is the one
    status run_search will not retry, so mislabelling a transient miss as a block
    turns it into a permanent failure for that request.
    """
    try:
        raw = await page.evaluate(_BLOCK_PROBE)
        info = json.loads(raw) if isinstance(raw, str) else raw
    except Exception:
        return False
    if not isinstance(info, dict):
        return False

    # A visible challenge widget is unambiguous.
    if info.get("widget"):
        return True

    # Otherwise require a challenge phrase *and* a page too small to be the app.
    if info.get("length", 0) > _BLOCK_TEXT_CEILING:
        return False
    haystack = f"{info.get('title', '')} {info.get('text', '')}".lower()
    return any(phrase in haystack for phrase in _BLOCK_PHRASES)


async def _get_body(page, request_id, attempts=3):
    """Fetch a response body, tolerating CDP's brief 'no resource' window.

    Network.loadingFinished can arrive before the body is retrievable (and for
    some prefetch/service-worker contexts it never is), so a bare single
    attempt silently loses otherwise-good responses.
    """
    for i in range(attempts):
        try:
            body = await page.send(zd.cdp.network.get_response_body(request_id=request_id))
            if body and body[0]:
                return body[0]
        except Exception:
            if i == attempts - 1:
                return None
            await asyncio.sleep(0.25)
    return None


# Resources a scraper never reads. Product images are taken as URLs out of the
# JSON payloads and DOM attributes, so the decoded pixels are pure cost: they
# dominate renderer memory on a grid of forty products and buy us nothing.
# Scripts are deliberately absent -- the sites' own WAF challenges are
# JavaScript, and blocking those would get us challenged rather than served.
BLOCKED_PATTERNS = [
    "*.jpg", "*.jpeg", "*.png", "*.gif", "*.webp", "*.avif", "*.bmp", "*.ico",
    "*.woff", "*.woff2", "*.ttf", "*.otf", "*.eot",
    "*.mp4", "*.webm", "*.avi", "*.mov", "*.mp3",
    # Third-party telemetry: fetched on every page, never read by us.
    "*google-analytics.com*", "*googletagmanager.com*", "*doubleclick.net*",
    "*facebook.net*", "*connect.facebook.com*", "*newrelic.com*",
    "*nr-data.net*", "*clarity.ms*", "*hotjar.com*", "*segment.io*",
    "*branch.io*", "*clevertap.com*", "*moengage.com*", "*mixpanel.com*",
]


# Network.enable is idempotent to the browser but not free to us: it is a CDP
# round trip, and every scrape asks for it two or three times over (once when
# the tab is prepared for resource blocking, once per interception attempt, and
# again on each retry). The domain stays enabled for the life of the tab, so
# remember it there rather than re-sending.
_NETWORK_ENABLED = "_quickcom_network_enabled"


async def enable_network(page):
    """Turn on Network domain events for this tab, at most once per tab."""
    if getattr(page, _NETWORK_ENABLED, False):
        return True
    try:
        await page.send(zd.cdp.network.enable())
    except Exception:
        return False
    try:
        setattr(page, _NETWORK_ENABLED, True)
    except Exception:
        # A page object that will not take attributes simply pays the round
        # trip again; correctness does not depend on the memo.
        pass
    return True


async def block_heavy_resources(page):
    """Stop the tab fetching bytes no scraper will ever look at.

    Cuts peak memory substantially on image-heavy product grids, and shortens
    page loads as a side effect. Best-effort: a browser that will not accept
    the command still works, just heavier.
    """
    try:
        await enable_network(page)
        await page.send(zd.cdp.network.set_blocked_ur_ls(urls=BLOCKED_PATTERNS))
        return True
    except Exception as e:
        print(f"[common] resource blocking unavailable: {type(e).__name__}: {e}")
        return False


# Used to tell "the grid has not arrived yet" from "there is no grid". A
# server-rendered result page ships its cards in the HTML, so a document that
# has finished loading without any is not going to grow some.
_DOCUMENT_COMPLETE_JS = "document.readyState === 'complete'"

# Poll schedule shared by the waiters below. Conditions that follow a
# navigation are usually satisfied within a few tens of milliseconds, so the
# first re-check happens quickly and the gap only grows towards the caller's
# interval if the page really is slow.
_POLL_START = 0.05
_POLL_GROWTH = 1.6


async def _poll(probe, timeout, interval):
    """Await `probe()` until it returns something truthy, or time runs out.

    Returns the truthy value, or None. Shared by the JS-predicate and
    cookie waiters so both get the same fast-first, backing-off schedule.
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    delay = min(_POLL_START, interval)
    while True:
        found = await probe()
        if found:
            return found
        remaining = deadline - loop.time()
        if remaining <= 0:
            return None
        await asyncio.sleep(min(delay, remaining))
        delay = min(delay * _POLL_GROWTH, interval)


async def wait_for(page, predicate_js, timeout=6.0, interval=0.25):
    """Poll a JS boolean expression until it is true, or the budget runs out.

    Returns whether it became true. Preferable to a flat sleep in either
    direction: it continues as soon as the page is ready, and it keeps waiting
    when the page is slower than the guess baked into a fixed interval.

    `interval` is the *ceiling* on the gap between polls, not the gap itself --
    a condition that comes true just after the first check is not charged a
    quarter-second for it.
    """
    expression = f"!!({predicate_js})"

    async def probe():
        try:
            return await page.evaluate(expression) is True
        except Exception:
            return False

    return await _poll(probe, timeout, interval) is True


async def wait_for_cookie(page, name, *, timeout=2.0, urls=None):
    """Wait for the browser to hold a cookie called `name`, and return it.

    The condition several set_location flows are really waiting on: the cookie
    the *server* sets in reply to a navigation, which a flat sleep can only
    guess the arrival of. Returns None when it never turns up inside the
    budget, which callers treat exactly as they treated the sleep expiring.
    """
    async def probe():
        try:
            cookies = await page.send(zd.cdp.network.get_cookies(urls=urls))
        except Exception:
            return None
        for cookie in cookies or []:
            if cookie.name == name:
                return cookie
        return None

    return await _poll(probe, timeout, 0.25)


async def _needs_warmup(page, origin):
    """True when this origin has no session cookies yet in the browser profile.

    The warmup navigation exists to let the site set its session and WAF
    cookies before the search request goes out. Those cookies live in the
    browser profile, not the tab, so once set_location has visited an origin
    every later tab already carries them and loading the homepage again is a
    wasted round trip -- measured at 3.3s per search on Instamart alone.

    Falls back to warming up whenever we cannot tell, so the cheap path is only
    taken on positive evidence.
    """
    cookies = await _origin_cookies(page, origin)
    if cookies is None:
        return True
    return not cookies


async def _origin_cookies(page, origin):
    """Cookies the profile holds for `origin`, or None if CDP would not say."""
    try:
        return await page.send(zd.cdp.network.get_cookies(urls=[origin]))
    except Exception:
        return None


async def _await_warmup(page, origin, ceiling):
    """Wait out a warmup navigation, but only for as long as it needs.

    The navigation exists to make the origin set its session and WAF cookies,
    so their existence -- not a fixed sleep -- is the condition that ends it.
    page.get() has already waited for the load to go quiet by the time we get
    here, so on a healthy origin this returns on the first check; `ceiling` is
    the old flat sleep, kept as the budget for an origin that is genuinely slow
    to hand out a session.
    """
    async def probe():
        return await _origin_cookies(page, origin)

    return await _poll(probe, ceiling, 0.25) is not None


async def intercept_json(
    page,
    *,
    tag,
    match,
    parse,
    navigate,
    warmup=None,
    warmup_wait=1.5,
    timeout=15.0,
    before_navigate=None,
):
    """Navigate to a search page and parse the JSON API behind it.

    `match(url)`      -> True for the API responses we care about
    `parse(payload)`  -> list of normalised product dicts (may be called more
                         than once; results accumulate until non-empty)
    `navigate`        -> the search URL to load
    `warmup`          -> origin URL to load first, so cookies/WAF tokens exist
                         before the search request goes out
    `before_navigate` -> awaitable run after warmup, before the search load
                         (used to set cookies on an established origin)

    Returns a ScrapeResult so callers can distinguish blocked from empty.
    """
    collected = []
    state = {"done": False, "blocked": False, "saw_api": False, "empty_at": None}
    targets = set()
    loop = asyncio.get_running_loop()
    # Handlers announce every state change the wait below cares about, so the
    # function returns the moment the payload is parsed. Polling for it instead
    # cost up to a tenth of a second per attempt, and run_search may make two.
    progress = asyncio.Event()

    async def on_response(event):
        if state["done"]:
            return
        url = event.response.url or ""
        # `match` runs for every response the tab receives -- hundreds on these
        # pages -- so ask it once and branch on the answer.
        if not match(url):
            return
        try:
            status = event.response.status
        except Exception:
            status = 200
        if status in _BLOCK_STATUSES:
            state["blocked"] = True
            progress.set()
            return
        state["saw_api"] = True
        targets.add(event.request_id)

    async def on_finished(event):
        if state["done"] or event.request_id not in targets:
            return
        targets.discard(event.request_id)
        raw = await _get_body(page, event.request_id)
        if not raw:
            return
        try:
            payload = json.loads(raw)
        except (ValueError, TypeError):
            return
        try:
            items = parse(payload) or []
        except Exception as e:
            print(f"[{tag}] parse error: {type(e).__name__}: {e}")
            return
        if items:
            collected.extend(items)
            state["done"] = True
        else:
            # The API answered with nothing. Note when, so the wait below can
            # give up early instead of sitting out the full timeout on a query
            # that genuinely has no matches.
            state["empty_at"] = loop.time()
        progress.set()

    await enable_network(page)

    if warmup and await _needs_warmup(page, warmup):
        try:
            await page.get(warmup)
            await _await_warmup(page, warmup, warmup_wait)
        except Exception:
            pass

    if before_navigate:
        try:
            await before_navigate()
        except Exception as e:
            print(f"[{tag}] pre-navigate hook failed: {type(e).__name__}: {e}")

    # Handlers go on after warmup so homepage traffic can't be mistaken for
    # search results.
    page.add_handler(zd.cdp.network.ResponseReceived, on_response)
    page.add_handler(zd.cdp.network.LoadingFinished, on_finished)

    try:
        try:
            await page.get(navigate)
        except Exception:
            pass

        deadline = loop.time() + timeout
        while True:
            # Cleared before the state is read, never after: a handler firing
            # in between sets it again, so a payload that lands while we are
            # working out how long to wait cannot be missed.
            progress.clear()
            if state["done"] or state["blocked"]:
                break
            budget = deadline - loop.time()
            if state["empty_at"] is not None:
                # Give a short grace period after an empty payload -- some
                # sites send the grid in a second, paginated response. Each
                # empty answer restarts that clock, as the poll loop did.
                budget = min(budget, state["empty_at"] + EMPTY_GRACE - loop.time())
            if budget <= 0:
                break
            try:
                await asyncio.wait_for(progress.wait(), budget)
            except asyncio.TimeoutError:
                pass
    finally:
        page.remove_handlers(zd.cdp.network.ResponseReceived)
        page.remove_handlers(zd.cdp.network.LoadingFinished)

    if collected:
        return ScrapeResult(collected, OK)

    if state["blocked"]:
        return ScrapeResult([], BLOCKED, "Platform rejected the request (bot protection).")

    if await _page_looks_blocked(page):
        return ScrapeResult([], BLOCKED, "Served a bot challenge instead of results.")

    if state["saw_api"]:
        # The API answered, we just could not find products in it. Either a
        # genuinely empty result set or the payload shape moved.
        return ScrapeResult([], EMPTY, "Search API returned no products.")

    return ScrapeResult([], TIMEOUT, "Search API never responded.")


async def scrape_dom(page, *, tag, navigate, extract, card_count=None, settle=6.0,
                     settle_min=1.2, timeout=20.0):
    """Load a server-rendered page and pull products out of its DOM.

    The counterpart to intercept_json for sites that ship HTML rather than
    calling a private API (Amazon). Shares the same block detection and
    ScrapeResult contract so callers cannot tell the two apart.

    `extract` is a JS expression evaluated in the page that must return a JSON
    string: an array of normalised product dicts.

    `card_count` is an optional JS expression returning how many product cards
    are currently rendered. Given one, the settle loop watches that number
    instead of re-running `extract`, and the full extraction happens once, when
    the grid has stopped growing.
    """
    loop = asyncio.get_running_loop()
    await enable_network(page)

    status = {"code": None}
    document_url = navigate.split("?")[0]

    async def on_response(event):
        # Only the top-level document status tells us we were turned away.
        url = event.response.url or ""
        if url.split("?")[0] == document_url:
            try:
                status["code"] = event.response.status
            except Exception:
                pass

    page.add_handler(zd.cdp.network.ResponseReceived, on_response)
    try:
        try:
            await asyncio.wait_for(page.get(navigate), timeout=timeout)
        except asyncio.TimeoutError:
            return ScrapeResult([], TIMEOUT, "Page did not finish loading.")
        except Exception as e:
            return ScrapeResult([], ERROR, f"{type(e).__name__}: {e}")

        # Poll for product cards rather than sleeping a flat interval: a
        # server-rendered page is usually ready well before the ceiling, and a
        # slow one gets the full budget instead of being read too early.
        #
        # Wait for the count to *stabilise*, not merely to become non-zero.
        # Amazon streams its grid in, so reading on the first card that appears
        # captured four products out of forty.
        items, last_error, previous = [], None, -1
        started = loop.time()
        deadline = started + settle
        # settle_min stops us accepting an early plateau: rendering pauses, so
        # two equal readings a moment apart is not proof the grid is complete.
        floor = started + settle_min

        async def pull_items():
            nonlocal last_error
            try:
                raw = await page.evaluate(extract)
                return json.loads(raw) if isinstance(raw, str) else (raw or [])
            except Exception as e:
                last_error = e
                return []

        async def probe_count():
            """How many cards are rendered, or None if we cannot count cheaply.

            Detecting stabilisation with `extract` means building and
            serialising the whole product array across CDP on every poll --
            twenty times over a slow Amazon scrape -- to learn one number.
            Falling back to it when the count expression fails keeps the
            behaviour of a page that will not answer the cheap question.
            """
            if not card_count:
                return None
            try:
                value = await page.evaluate(card_count)
            except Exception:
                return None
            return value if isinstance(value, (int, float)) else None

        async def document_complete():
            try:
                return await page.evaluate(_DOCUMENT_COMPLETE_JS) is True
            except Exception:
                return False

        while True:
            fresh = False
            count = await probe_count()
            if count is None:
                items = await pull_items()
                count, fresh = len(items), True
            now = loop.time()
            settled = count > 0 and count == previous and now >= floor
            expired = now >= deadline
            if (settled or expired) and not fresh:
                items = await pull_items()
            if expired or (settled and items):
                break
            # Two empty readings past the floor on a document that has finished
            # loading is a page with no results, not a page still filling in.
            # Sitting out the rest of the settle budget on that is what made an
            # empty Amazon grocery search cost six seconds before the widened
            # retry it always needs next could even start.
            if count == 0 and previous == 0 and now >= floor and await document_complete():
                break
            previous = count
            await asyncio.sleep(0.3)
    finally:
        page.remove_handlers(zd.cdp.network.ResponseReceived)

    if status["code"] in _BLOCK_STATUSES:
        return ScrapeResult([], BLOCKED, f"Rejected with HTTP {status['code']}.")

    if not items and await _page_looks_blocked(page):
        return ScrapeResult([], BLOCKED, "Served a bot challenge instead of results.")

    if not items and last_error is not None:
        return ScrapeResult([], ERROR, f"extract failed: {type(last_error).__name__}: {last_error}")

    if not items:
        return ScrapeResult([], EMPTY, "Page contained no product cards.")
    return ScrapeResult(list(items), OK)


async def run_search(page, search_term, attempt_fn, *, tag, attempts=2):
    """Run a scraper's interception attempt, retrying once on a soft failure.

    Interception is timing-sensitive -- a missed response used to mean an empty
    column with no explanation. A single cheap retry recovers most of those.
    """
    result = ScrapeResult([], ERROR, "not run")
    for i in range(attempts):
        try:
            result = await attempt_fn()
        except Exception as e:
            result = ScrapeResult([], ERROR, f"{type(e).__name__}: {e}")
            print(f"[{tag}] attempt {i + 1} raised: {type(e).__name__}: {e}")
        if result.status == OK and result.products:
            break
        # EMPTY means the API already answered -- asking again just burns
        # another full timeout. Everything else is worth one more go, blocks
        # included: these WAF challenges are usually negotiated by the browser
        # on the next load rather than being a standing ban.
        if result.status == EMPTY:
            break
        if i < attempts - 1:
            backoff = 3.0 if result.status == BLOCKED else 1.0
            print(f"[{tag}] attempt {i + 1} gave {result.status}, retrying in {backoff}s")
            await asyncio.sleep(backoff)

    # Keep a pool rather than trimming to MAX_PRODUCTS here: the API layer
    # applies the caller's sort/filter over these candidates and caps the
    # visible list. Order is the relevance ranking, which is the default view.
    ranked = rank_by_relevance(dedupe(result.products), search_term)[:POOL_SIZE]
    result.products = annotate_discounts(ranked)
    if result.status == OK and not result.products:
        result.status = EMPTY
    print(f"[{tag}] {result.status}: {len(result.products)} products")
    return result
