import pytest
from backend_py.server import SERVICES

def test_services_list():
    assert "blinkit" in SERVICES
    assert "bigbasket" in SERVICES
    assert "jiomart" in SERVICES
    assert "zepto" in SERVICES
    assert "instamart" in SERVICES
