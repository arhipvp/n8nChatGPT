import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import main


class DummyResponse:
    def __init__(self, tunnels):
        self._tunnels = tunnels
        self.status_code = 200

    def raise_for_status(self):
        return None

    def json(self):
        return {"tunnels": self._tunnels}


def _make_tunnel(addr):
    return {
        "proto": "https",
        "config": {"addr": addr},
        "public_url": "https://example.ngrok.app",
    }


def _run_with_addr(addr):
    response = DummyResponse([_make_tunnel(addr)])
    with patch.object(main.requests, "get", return_value=response):
        return main.get_ngrok_url(timeout=0.1)


def test_get_ngrok_url_accepts_ipv4_loopback():
    assert _run_with_addr("127.0.0.1:8000") == "https://example.ngrok.app"


def test_get_ngrok_url_accepts_localhost():
    assert _run_with_addr("http://localhost:8000") == "https://example.ngrok.app"


def test_get_ngrok_url_accepts_ipv6_loopback_with_scheme():
    assert _run_with_addr("http://[::1]:8000") == "https://example.ngrok.app"


def test_get_ngrok_url_accepts_ipv6_loopback_without_scheme():
    assert _run_with_addr("[::1]:8000") == "https://example.ngrok.app"
