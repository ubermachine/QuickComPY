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
    q = _tokens(query)
    if not q:
        return 0.0
    name_tokens = _tokens(name)
    if not name_tokens:
        return 0.0
    haystack = (name or "").lower()

    score = 0.0
    for t in q:
        if t in name_tokens:
            score += 1.0
            idx = name_tokens.index(t)
            score += 0.5 * (1.0 - idx / len(name_tokens))
        elif t in haystack:
            score += 0.5
    if score == 0.0:
        return 0.0

    # Length penalty, capped so a very long title cannot go negative and end up
    # below a genuine non-match.
    return score - min(len(name_tokens), 20) * 0.02


def rank_by_relevance(products, query):
    """Stable-sort products so on-topic items outrank sponsored filler.

    Platforms inject ads at position 0 (Blinkit will happily lead a "milk"
    search with cake rusk). Sorting is stable, so within one score band the
    platform's own ordering survives.
    """
    if not products:
        return products
    scored = [(relevance_score(p.get("name"), query), i, p) for i, p in enumerate(products)]
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


async def _page_looks_blocked(page):
    """True when the current document is a bot challenge rather than the site.

    Deliberately conservative. A false positive is expensive: BLOCKED is the one
    status run_search will not retry, so mislabelling a transient miss as a block
    turns it into a permanent failure for that request.
    """
    try:
        raw = await page.evaluate(_BLOCK_PROBE_JS % json.dumps(list(_BLOCK_SELECTORS)))
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

    async def on_response(event):
        if state["done"]:
            return
        url = event.response.url or ""
        try:
            status = event.response.status
        except Exception:
            status = 200
        if status in _BLOCK_STATUSES and match(url):
            state["blocked"] = True
            return
        if match(url):
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
            # The API answered with nothing. Note when, so the wait loop can
            # give up early instead of sitting out the full timeout on a query
            # that genuinely has no matches.
            state["empty_at"] = loop.time()

    try:
        await page.send(zd.cdp.network.enable())
    except Exception:
        pass

    if warmup:
        try:
            await page.get(warmup)
            await asyncio.sleep(warmup_wait)
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
        while not state["done"] and loop.time() < deadline:
            if state["blocked"]:
                break
            # Give a short grace period after an empty payload -- some sites
            # send the grid in a second, paginated response.
            if state["empty_at"] and loop.time() - state["empty_at"] > EMPTY_GRACE:
                break
            await asyncio.sleep(0.1)
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


async def scrape_dom(page, *, tag, navigate, extract, settle=2.5, timeout=20.0):
    """Load a server-rendered page and pull products out of its DOM.

    The counterpart to intercept_json for sites that ship HTML rather than
    calling a private API (Amazon). Shares the same block detection and
    ScrapeResult contract so callers cannot tell the two apart.

    `extract` is a JS expression evaluated in the page that must return a JSON
    string: an array of normalised product dicts.
    """
    try:
        await page.send(zd.cdp.network.enable())
    except Exception:
        pass

    status = {"code": None}

    async def on_response(event):
        # Only the top-level document status tells us we were turned away.
        url = event.response.url or ""
        if url.split("?")[0] == navigate.split("?")[0]:
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
        await asyncio.sleep(settle)
    finally:
        page.remove_handlers(zd.cdp.network.ResponseReceived)

    if status["code"] in _BLOCK_STATUSES:
        return ScrapeResult([], BLOCKED, f"Rejected with HTTP {status['code']}.")

    if await _page_looks_blocked(page):
        return ScrapeResult([], BLOCKED, "Served a bot challenge instead of results.")

    try:
        raw = await page.evaluate(extract)
    except Exception as e:
        return ScrapeResult([], ERROR, f"extract failed: {type(e).__name__}: {e}")

    try:
        items = json.loads(raw) if isinstance(raw, str) else (raw or [])
    except (ValueError, TypeError) as e:
        return ScrapeResult([], ERROR, f"extract returned non-JSON: {e}")

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

    result.products = rank_by_relevance(dedupe(result.products), search_term)[:MAX_PRODUCTS]
    if result.status == OK and not result.products:
        result.status = EMPTY
    print(f"[{tag}] {result.status}: {len(result.products)} products")
    return result
