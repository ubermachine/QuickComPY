"""Tests for the Swiggy Instamart scraper's location flow.

No browser: a fake tab records the order of what set_location does to it.
"""

import os
import sys

_project_root = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from backend_py.scrapers import instamart


class RecordingPage:
    def __init__(self, log):
        self.log = log

    async def send(self, _command):
        self.log.append("send")

    async def get(self, url, **_kw):
        self.log.append(f"get {url}")
        return self

    async def evaluate(self, _expression, **_kw):
        return True


async def test_set_location_gives_swiggy_its_full_bootstrap_before_releasing_the_tab(monkeypatch):
    """Guards the #12 regression: a condition that came true at once replaced
    this sleep, and Instamart answered 3 of 4 live searches with an empty grid.
    """
    log = []

    async def fake_sleep(seconds):
        log.append(f"sleep {seconds}")

    monkeypatch.setattr(instamart.asyncio, "sleep", fake_sleep)

    assert await instamart.set_location(RecordingPage(log), "201306") is True

    loaded = log.index("get https://www.swiggy.com/instamart")
    slept = log.index(f"sleep {instamart.SESSION_BOOTSTRAP}")
    assert loaded < slept < len(log) - 1, f"sleep must follow the load and precede the cookie: {log}"
    assert log[-1] == "send", "the userLocation cookie is set last, after the bootstrap"
    assert instamart.SESSION_BOOTSTRAP >= 2.0, "2s is the measured floor; shorter broke live searches"
