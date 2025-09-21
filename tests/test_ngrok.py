import types

import runtime


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
    requests_stub = types.SimpleNamespace(get=lambda *args, **kwargs: response)
    tunnel = runtime.NgrokTunnel(
        port=runtime.PORT,
        root=runtime.ROOT,
        requests_module=requests_stub,
    )
    return tunnel.get_public_url(timeout=0.1)


def test_get_ngrok_url_accepts_ipv4_loopback():
    assert _run_with_addr("127.0.0.1:8000") == "https://example.ngrok.app"


def test_get_ngrok_url_accepts_localhost():
    assert _run_with_addr("http://localhost:8000") == "https://example.ngrok.app"


def test_get_ngrok_url_accepts_ipv6_loopback_with_scheme():
    assert _run_with_addr("http://[::1]:8000") == "https://example.ngrok.app"


def test_get_ngrok_url_accepts_ipv6_loopback_without_scheme():
    assert _run_with_addr("[::1]:8000") == "https://example.ngrok.app"


def test_find_ngrok_exe_uses_root_when_cwd_changes(tmp_path, monkeypatch):
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    exe = project_dir / "ngrok.exe"
    exe.write_text("dummy")

    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    tunnel = runtime.NgrokTunnel(port=runtime.PORT, root=project_dir)
    assert tunnel.find_executable() == str(exe)
