"""Tests for the timing machinery in backend_py/scrapers/common.py.

These drive `intercept_json`, `scrape_dom` and the waiters against a fake tab
that answers the handful of CDP calls they make, so the parts of the scrapers
that are pure scheduling can be tested without a browser.

They are mostly regression guards against latency creeping back in: the engine
used to poll for the intercepted payload on a 100ms tick, re-run the whole DOM
extractor every 300ms just to count what it returned, and sleep out a flat
warmup even on an origin that had already answered. Each of those is cheap to
reintroduce and invisible in a functional test, so the assertions below are
about *when* the engine returns, not only what it returns.
"""

import asyncio
import json
import os
import sys
import time
from types import SimpleNamespace

_project_root = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import zendriver as zd

from backend_py.scrapers import common


API_URL = "https://api.test/v1/search?q=milk"
SEARCH_URL = "https://shop.test/search?q=milk"
ORIGIN = "https://shop.test/"

# A page that is plainly the real app, so _page_looks_blocked says no.
_HEALTHY_PROBE = {
    "widget": None,
    "title": "milk - Shop",
    "text": "Amul Gold Full Cream Milk " * 300,
    "length": 8000,
}


def _cookie(name="session", value="1"):
    return SimpleNamespace(name=name, value=value)


def _payload(n=3):
    return json.dumps({"products": [{"name": f"Milk {i}", "id": str(i)} for i in range(n)]})


def _parse(payload):
    return list(payload.get("products") or [])


def _match(url):
    return "/v1/search" in url


class FakePage:
    """A zendriver tab reduced to what the interception engine touches.

    CDP commands arrive as generators, which is how `send` tells them apart --
    the same way the real Tab does, minus a browser.
    """

    def __init__(self, *, cookies=(), probe=None, on_navigate=None):
        self.url = "about:blank"
        self.handlers = {}
        self.navigations = []
        self.cookies = list(cookies)
        self.bodies = {}
        self.enable_calls = 0
        self.body_calls = 0
        self.evaluations = []
        self.on_navigate = on_navigate
        self.probe = probe if probe is not None else _HEALTHY_PROBE

    # -- CDP -----------------------------------------------------------------

    async def send(self, cmd):
        name = cmd.gi_code.co_name
        args = dict(cmd.gi_frame.f_locals)
        cmd.close()
        if name == "enable":
            self.enable_calls += 1
            return None
        if name == "get_cookies":
            return list(self.cookies)
        if name == "get_response_body":
            self.body_calls += 1
            body = self.bodies.get(args.get("request_id"))
            return (body, False) if body is not None else None
        return None

    def add_handler(self, event_type, handler):
        self.handlers.setdefault(event_type, []).append(handler)

    def remove_handlers(self, event_type=None, handler=None):
        if event_type is None:
            self.handlers.clear()
        else:
            self.handlers.pop(event_type, None)

    # -- navigation and evaluation -------------------------------------------

    async def get(self, url):
        self.url = url
        self.navigations.append(url)
        await asyncio.sleep(0)
        if self.on_navigate:
            await self.on_navigate(self, url)
        return self

    async def evaluate(self, expression, **_kw):
        self.evaluations.append(expression)
        return json.dumps(self.probe)

    # -- test helpers ---------------------------------------------------------

    async def deliver(self, body, *, url=API_URL, status=200, request_id=None, delay=0.0):
        """Push one API response through the handlers, as CDP would."""
        if delay:
            await asyncio.sleep(delay)
        request_id = request_id or f"req-{len(self.bodies) + 1}"
        if body is not None:
            self.bodies[request_id] = body
        response = SimpleNamespace(url=url, status=status)
        for handler in list(self.handlers.get(zd.cdp.network.ResponseReceived, [])):
            await handler(SimpleNamespace(request_id=request_id, response=response))
        for handler in list(self.handlers.get(zd.cdp.network.LoadingFinished, [])):
            await handler(SimpleNamespace(request_id=request_id))

    def answer_with(self, *deliveries):
        """Schedule responses to land *after* the search navigation returns.

        Handlers run as their own tasks under real CDP, so a payload that
        arrives while the engine is waiting is the case worth testing -- it is
        the one a polling loop reacted to late.
        """
        async def _navigate(page, url):
            if url != SEARCH_URL:
                return
            for kwargs in deliveries:
                asyncio.ensure_future(page.deliver(**kwargs))

        self.on_navigate = _navigate
        return self


def _run(coro):
    return asyncio.run(coro)


async def _intercept(page, **kwargs):
    kwargs.setdefault("tag", "Test")
    kwargs.setdefault("match", _match)
    kwargs.setdefault("parse", _parse)
    kwargs.setdefault("navigate", SEARCH_URL)
    return await common.intercept_json(page, **kwargs)


class _Clock:
    """Wall-clock stopwatch for the 'how long did that take' assertions."""

    def __enter__(self):
        self.start = time.monotonic()
        return self

    def __exit__(self, *exc):
        self.elapsed = time.monotonic() - self.start
        return False


# ---------------------------------------------------------------------------
# intercept_json: event-driven, not polled
# ---------------------------------------------------------------------------

def test_interception_returns_the_parsed_payload():
    page = FakePage().answer_with({"body": _payload(3)})
    result = _run(_intercept(page, timeout=5.0))
    assert result.status == common.OK
    assert [p["name"] for p in result.products] == ["Milk 0", "Milk 1", "Milk 2"]


def test_interception_returns_the_instant_the_payload_is_parsed():
    """Regression guard: a 100ms poll would charge every scrape for the tick.

    The payload lands while the engine is waiting, which is the case a polling
    loop noticed late -- up to a tenth of a second late, twice over when
    run_search retries.
    """
    page = FakePage().answer_with({"body": _payload()})
    with _Clock() as clock:
        result = _run(_intercept(page, timeout=30.0))
    assert result.status == common.OK
    assert clock.elapsed < 0.05, f"waited {clock.elapsed:.3f}s for a payload already in hand"


def test_interception_does_not_sleep_on_a_timer(monkeypatch):
    """The same guard, expressed without a stopwatch.

    Nothing on the happy path may wait on a duration: the handlers say when
    they are done. A poll-based implementation cannot satisfy this.
    """
    slept = []
    real_sleep = asyncio.sleep

    async def spy(delay, *a, **kw):
        if delay:
            slept.append(delay)
        return await real_sleep(delay, *a, **kw)

    monkeypatch.setattr(common.asyncio, "sleep", spy)
    page = FakePage().answer_with({"body": _payload()})
    result = _run(_intercept(page, timeout=30.0))
    assert result.status == common.OK
    assert slept == [], f"interception slept on a timer: {slept}"


def test_interception_survives_a_payload_that_lands_late():
    page = FakePage().answer_with({"body": _payload(), "delay": 0.2})
    with _Clock() as clock:
        result = _run(_intercept(page, timeout=30.0))
    assert result.status == common.OK
    assert 0.2 <= clock.elapsed < 1.0


def test_interception_times_out_when_the_api_never_answers():
    page = FakePage()
    with _Clock() as clock:
        result = _run(_intercept(page, timeout=0.3))
    assert result.status == common.TIMEOUT
    assert 0.3 <= clock.elapsed < 1.5


def test_unmatched_responses_are_ignored():
    page = FakePage().answer_with({"body": _payload(), "url": "https://cdn.test/telemetry"})
    result = _run(_intercept(page, timeout=0.3))
    assert result.status == common.TIMEOUT


def test_blocking_status_ends_the_wait_immediately():
    page = FakePage().answer_with({"body": None, "status": 403})
    with _Clock() as clock:
        result = _run(_intercept(page, timeout=30.0))
    assert result.status == common.BLOCKED
    assert clock.elapsed < 0.05, "a rejected request should not be waited out"


def test_a_challenge_page_is_reported_as_blocked():
    page = FakePage(probe={"widget": "#captchacharacters", "title": "", "text": "", "length": 10})
    result = _run(_intercept(page, timeout=0.2))
    assert result.status == common.BLOCKED


def test_empty_payload_ends_the_wait_after_the_grace_period(monkeypatch):
    """An empty answer is an answer; the timeout is not the budget for it."""
    monkeypatch.setattr(common, "EMPTY_GRACE", 0.3)
    page = FakePage().answer_with({"body": json.dumps({"products": []})})
    with _Clock() as clock:
        result = _run(_intercept(page, timeout=30.0))
    assert result.status == common.EMPTY
    assert 0.3 <= clock.elapsed < 1.5, f"grace period not honoured ({clock.elapsed:.3f}s)"


def test_a_paginated_grid_arriving_within_the_grace_period_still_counts():
    """The reason the grace period exists: the first page can be empty."""
    page = FakePage().answer_with(
        {"body": json.dumps({"products": []})},
        {"body": _payload(2), "delay": 0.15},
    )
    result = _run(_intercept(page, timeout=30.0))
    assert result.status == common.OK
    assert len(result.products) == 2


def test_each_empty_answer_restarts_the_grace_clock(monkeypatch):
    """Matching the poll loop it replaced, which re-read empty_at every tick."""
    monkeypatch.setattr(common, "EMPTY_GRACE", 0.3)
    page = FakePage().answer_with(
        {"body": json.dumps({"products": []})},
        {"body": json.dumps({"products": []}), "delay": 0.2},
        {"body": _payload(1), "delay": 0.4},
    )
    result = _run(_intercept(page, timeout=30.0))
    assert result.status == common.OK


def test_handlers_are_removed_whatever_happens():
    """A stray handler keeps firing for the rest of the scrape's navigations and
    leaks the closure holding its results, so this is not just hygiene."""
    page = FakePage().answer_with({"body": _payload()})
    _run(_intercept(page, timeout=5.0))
    assert page.handlers == {}

    page = FakePage()
    _run(_intercept(page, timeout=0.2))
    assert page.handlers == {}


def test_a_parse_error_does_not_end_the_scrape():
    def boom(_payload):
        raise ValueError("payload shape moved")

    page = FakePage().answer_with({"body": _payload()})
    result = _run(_intercept(page, parse=boom, timeout=0.3))
    assert result.status == common.EMPTY


def test_a_body_that_never_arrives_is_not_fatal():
    page = FakePage().answer_with({"body": None})
    result = _run(_intercept(page, timeout=0.3))
    assert result.status == common.EMPTY
    assert page.body_calls >= 1


# ---------------------------------------------------------------------------
# Warmup
# ---------------------------------------------------------------------------

def test_warmup_is_skipped_when_the_origin_already_has_cookies():
    page = FakePage(cookies=[_cookie()]).answer_with({"body": _payload()})
    _run(_intercept(page, warmup=ORIGIN, warmup_wait=5.0, timeout=5.0))
    assert page.navigations == [SEARCH_URL]


def test_warmup_waits_for_the_session_cookie_not_the_clock():
    """The warmup navigation exists to get cookies; once they exist it is done."""
    async def _navigate(page, url):
        if url == ORIGIN:
            page.cookies = [_cookie()]

    page = FakePage(on_navigate=_navigate)

    async def scenario():
        original = page.on_navigate

        async def both(p, url):
            await original(p, url)
            if url == SEARCH_URL:
                asyncio.ensure_future(p.deliver(body=_payload()))

        page.on_navigate = both
        return await _intercept(page, warmup=ORIGIN, warmup_wait=5.0, timeout=30.0)

    with _Clock() as clock:
        result = _run(scenario())
    assert result.status == common.OK
    assert page.navigations == [ORIGIN, SEARCH_URL]
    assert clock.elapsed < 0.5, f"charged for the warmup ceiling ({clock.elapsed:.3f}s)"


def test_warmup_still_honours_its_ceiling_when_no_cookie_appears():
    page = FakePage().answer_with({"body": _payload()})
    with _Clock() as clock:
        result = _run(_intercept(page, warmup=ORIGIN, warmup_wait=0.4, timeout=30.0))
    assert result.status == common.OK
    assert 0.4 <= clock.elapsed < 2.0


def test_before_navigate_runs_after_warmup_and_before_the_search():
    order = []

    async def _navigate(page, url):
        order.append(f"get:{url}")
        if url == SEARCH_URL:
            asyncio.ensure_future(page.deliver(body=_payload()))

    page = FakePage(cookies=[_cookie()], on_navigate=_navigate)

    async def hook():
        order.append("hook")

    _run(_intercept(page, warmup=ORIGIN, before_navigate=hook, timeout=5.0))
    assert order == ["hook", f"get:{SEARCH_URL}"]


# ---------------------------------------------------------------------------
# Network.enable is paid for once per tab
# ---------------------------------------------------------------------------

def test_network_is_enabled_once_per_tab():
    """Two attempts on one tab, one round trip -- the domain stays enabled."""
    async def scenario():
        page = FakePage().answer_with({"body": _payload()})
        await _intercept(page, timeout=5.0)
        await _intercept(page, timeout=5.0)
        return page

    page = _run(scenario())
    assert page.enable_calls == 1


def test_resource_blocking_reuses_the_same_enable():
    async def scenario():
        page = FakePage().answer_with({"body": _payload()})
        await common.block_heavy_resources(page)
        await _intercept(page, timeout=5.0)
        return page

    page = _run(scenario())
    assert page.enable_calls == 1


# ---------------------------------------------------------------------------
# scrape_dom: settle on a cheap count, extract once
# ---------------------------------------------------------------------------

COUNT_JS = "__count__"
EXTRACT_JS = "__extract__"


class DomPage(FakePage):
    """A page whose card count follows a schedule, as a streaming grid does."""

    def __init__(self, schedule, *, count_raises=False, document_complete=True, **kw):
        super().__init__(**kw)
        # schedule: ((elapsed_seconds, card_count), ...) applied in order.
        self.schedule = schedule
        self.count_raises = count_raises
        self.document_complete = document_complete
        self.count_calls = 0
        self.extract_calls = 0
        self.started = None

    def _cards_now(self):
        if self.started is None:
            self.started = time.monotonic()
        elapsed = time.monotonic() - self.started
        count = 0
        for at, value in self.schedule:
            if elapsed >= at:
                count = value
        return count

    async def evaluate(self, expression, **_kw):
        self.evaluations.append(expression)
        if expression == COUNT_JS:
            self.count_calls += 1
            if self.count_raises:
                raise RuntimeError("no such node")
            return self._cards_now()
        if expression == EXTRACT_JS:
            self.extract_calls += 1
            return json.dumps([{"name": f"Card {i}"} for i in range(self._cards_now())])
        if expression == common._DOCUMENT_COMPLETE_JS:
            return self.document_complete
        return json.dumps(self.probe)


async def _dom(page, **kwargs):
    kwargs.setdefault("tag", "Test")
    kwargs.setdefault("navigate", SEARCH_URL)
    kwargs.setdefault("extract", EXTRACT_JS)
    kwargs.setdefault("settle", 2.0)
    kwargs.setdefault("settle_min", 0.4)
    return await common.scrape_dom(page, **kwargs)


def test_dom_extraction_runs_once_when_the_count_has_settled():
    """The point of the count probe: one full extraction, not one per poll."""
    page = DomPage(((0.0, 12),))
    result = _run(_dom(page, card_count=COUNT_JS))
    assert result.status == common.OK
    assert len(result.products) == 12
    assert page.extract_calls == 1, f"extracted {page.extract_calls} times"
    assert page.count_calls >= 2, "the count is what should be polled"


def test_dom_extraction_waits_for_a_streaming_grid_to_stop_growing():
    """Amazon streams its grid; reading on the first card loses the rest."""
    page = DomPage(((0.0, 4), (0.3, 40)))
    result = _run(_dom(page, card_count=COUNT_JS))
    assert len(result.products) == 40
    assert page.extract_calls == 1


def test_dom_extraction_respects_the_settle_floor():
    """A plateau before settle_min is not proof the grid is complete."""
    page = DomPage(((0.0, 8),))
    with _Clock() as clock:
        result = _run(_dom(page, card_count=COUNT_JS, settle_min=0.6))
    assert len(result.products) == 8
    assert clock.elapsed >= 0.6


def test_dom_extraction_falls_back_when_the_count_cannot_be_read():
    page = DomPage(((0.0, 5),), count_raises=True)
    result = _run(_dom(page, card_count=COUNT_JS))
    assert len(result.products) == 5
    assert page.extract_calls > 1, "without a usable count, extraction settles it"


def test_dom_extraction_without_a_count_expression_is_unchanged():
    page = DomPage(((0.0, 5),))
    result = _run(_dom(page))
    assert len(result.products) == 5
    assert page.count_calls == 0
    assert page.extract_calls > 1


def test_dom_reports_empty_when_no_cards_ever_render():
    page = DomPage(((0.0, 0),))
    result = _run(_dom(page, card_count=COUNT_JS, settle=0.6))
    assert result.status == common.EMPTY


def test_dom_gives_up_early_on_a_finished_page_with_no_cards():
    """Amazon's grocery index misses often, and the widened retry that always
    follows should not have to wait out a settle budget for a page that has
    already finished loading with nothing in it."""
    page = DomPage(((0.0, 0),))
    with _Clock() as clock:
        result = _run(_dom(page, card_count=COUNT_JS, settle=6.0, settle_min=0.4))
    assert result.status == common.EMPTY
    assert clock.elapsed < 2.0, f"waited {clock.elapsed:.1f}s on an empty finished page"


def test_dom_keeps_waiting_while_the_document_is_still_loading():
    """The early exit must not fire on a grid that has not been served yet."""
    page = DomPage(((0.0, 0), (0.8, 6)), document_complete=False)
    result = _run(_dom(page, card_count=COUNT_JS, settle=3.0, settle_min=0.4))
    assert result.status == common.OK
    assert len(result.products) == 6


def test_dom_reports_blocked_on_a_rejecting_status():
    page = DomPage(((0.0, 0),))

    async def _navigate(p, url):
        for handler in list(p.handlers.get(zd.cdp.network.ResponseReceived, [])):
            await handler(SimpleNamespace(
                request_id="doc", response=SimpleNamespace(url=url, status=503),
            ))

    page.on_navigate = _navigate
    result = _run(_dom(page, card_count=COUNT_JS, settle=0.6))
    assert result.status == common.BLOCKED
    assert "503" in result.message


def test_dom_removes_its_handler():
    page = DomPage(((0.0, 3),))
    _run(_dom(page, card_count=COUNT_JS))
    assert page.handlers == {}


# ---------------------------------------------------------------------------
# Waiters
# ---------------------------------------------------------------------------

class _TimedPage:
    """A predicate that becomes true a fixed time after the first poll."""

    def __init__(self, after):
        self.after = after
        self.started = None
        self.calls = 0

    async def evaluate(self, _expression, **_kw):
        self.calls += 1
        if self.started is None:
            self.started = time.monotonic()
        return time.monotonic() - self.started >= self.after


def test_wait_for_does_not_charge_the_full_interval_for_a_quick_condition():
    """The interval is a ceiling. A condition satisfied 20ms after the
    navigation used to wait out a quarter second regardless."""
    page = _TimedPage(0.02)
    with _Clock() as clock:
        assert _run(common.wait_for(page, "ready", timeout=5.0)) is True
    assert clock.elapsed < 0.15, f"waited {clock.elapsed:.3f}s for a 20ms condition"


def test_wait_for_backs_off_rather_than_spinning():
    """Cheap for a fast condition must not mean hammering a slow one."""
    page = _TimedPage(1.0)
    assert _run(common.wait_for(page, "ready", timeout=3.0)) is True
    assert page.calls < 25, f"{page.calls} polls to cover one second"


def test_wait_for_still_reports_failure_at_the_deadline():
    page = _TimedPage(10.0)
    with _Clock() as clock:
        assert _run(common.wait_for(page, "ready", timeout=0.3)) is False
    assert 0.3 <= clock.elapsed < 1.0


def test_wait_for_cookie_returns_the_cookie_as_soon_as_it_lands():
    page = FakePage()

    async def scenario():
        async def set_later():
            await asyncio.sleep(0.1)
            page.cookies = [_cookie("serviceability", "%7B%22serviceable%22%3Afalse%7D")]

        asyncio.ensure_future(set_later())
        return await common.wait_for_cookie(page, "serviceability", timeout=5.0)

    with _Clock() as clock:
        cookie = _run(scenario())
    assert cookie is not None and cookie.name == "serviceability"
    assert 0.1 <= clock.elapsed < 0.6


def test_wait_for_cookie_gives_up_at_its_ceiling():
    page = FakePage(cookies=[_cookie("other")])
    with _Clock() as clock:
        assert _run(common.wait_for_cookie(page, "serviceability", timeout=0.3)) is None
    assert 0.3 <= clock.elapsed < 1.0


def test_wait_for_cookie_tolerates_a_failing_tab():
    class Broken(FakePage):
        async def send(self, cmd):
            cmd.close()
            raise RuntimeError("target closed")

    assert _run(common.wait_for_cookie(Broken(), "x", timeout=0.2)) is None
