import asyncio
import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

pytest.importorskip("fastmcp")

import server


@pytest.fixture(scope="module")
def client():
    return TestClient(server.app.http_app())


@pytest.mark.parametrize("path", ["/", "/.well-known/mcp.json"])
def test_manifest_endpoints_return_manifest_json(client, path):
    response = client.get(path)

    assert response.status_code == 200
    assert response.headers.get("content-type", "").startswith("application/json")

    payload = response.json()
    for key in ("mcp", "server", "tools"):
        assert key in payload

    capabilities = payload.get("capabilities", {})
    search_info = capabilities.get("search", {})
    assert search_info.get("enabled") is False
    assert search_info.get("reason") == "SEARCH_API_URL is not configured"


def test_manifest_search_capability_enabled_when_url(monkeypatch, client):
    monkeypatch.setattr(server, "SEARCH_API_URL", "https://example.com/search")

    response = client.get("/")

    assert response.status_code == 200

    payload = response.json()
    search_info = payload.get("capabilities", {}).get("search", {})
    assert search_info.get("enabled") is True
    assert "reason" not in search_info


def test_manifest_routes_without_fastapi(monkeypatch):
    """Проверяем, что сервер отвечает корректным JSON даже без FastAPI."""

    def _missing_attr(name: str):
        raise AttributeError(name)

    for module_name in ("fastapi", "fastapi.responses", "starlette.responses"):
        missing_module = types.ModuleType(module_name)
        missing_module.__getattr__ = _missing_attr  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, module_name, missing_module)

    server_path = Path(__file__).resolve().parents[1] / "server.py"
    spec = importlib.util.spec_from_file_location("server_without_fastapi", server_path)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    response = asyncio.run(module._manifest_response())

    scope = {"type": "http", "method": "GET", "path": "/", "headers": []}
    captured = {"headers": {}}
    body_chunks = []

    async def send(message):
        if message["type"] == "http.response.start":
            captured["status"] = message["status"]
            captured["headers"] = {
                name.decode("latin-1"): value.decode("latin-1")
                for name, value in message.get("headers", [])
            }
        elif message["type"] == "http.response.body":
            body_chunks.append(message.get("body") or b"")

    async def receive():
        return {"type": "http.request"}

    asyncio.run(response(scope, receive, send))

    assert captured.get("status") == 200
    assert captured["headers"].get("content-type", "").startswith("application/json")

    payload = json.loads(b"".join(body_chunks).decode("utf-8"))
    for key in ("mcp", "server", "tools"):
        assert key in payload
    capabilities = payload.get("capabilities", {})
    search_info = capabilities.get("search", {})
    assert search_info.get("enabled") is False
