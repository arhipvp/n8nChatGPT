import asyncio
import base64
import sys
import types
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image


def _field_stub(*args, **kwargs):
    if "default" in kwargs:
        return kwargs["default"]
    if "default_factory" in kwargs:
        return kwargs["default_factory"]()
    return None


try:  # pragma: no cover - exercised only when dependency missing
    import fastmcp as _fastmcp_mod  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - executed in minimal test environments
    def _noop_decorator(*args, **kwargs):
        def decorator(func):
            return func

        return decorator

    fastmcp_stub = types.SimpleNamespace(
        FastMCP=lambda *args, **kwargs: types.SimpleNamespace(
            tool=_noop_decorator,
            custom_route=_noop_decorator,
            name=kwargs.get("name", args[0] if args else "anki-mcp"),
        )
    )
    sys.modules.setdefault("fastmcp", fastmcp_stub)

try:  # pragma: no cover - exercised only when dependency missing
    import pydantic as _pydantic_mod  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - executed in minimal test environments
    pydantic_stub = types.SimpleNamespace(
        BaseModel=object,
        Field=_field_stub,
        constr=lambda **kwargs: str,
        AnyHttpUrl=str,
    )
    sys.modules.setdefault("pydantic", pydantic_stub)

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import server


class DummyResponse:
    def __init__(self, content: bytes, status_code: int = 200, headers: dict | None = None):
        self.content = content
        self.status_code = status_code
        self.headers = headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP error {self.status_code}")


class DummyAsyncClient:
    def __init__(self, response: DummyResponse):
        self._response = response

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url: str):
        return self._response


class DummyRedirectAsyncClient:
    def __init__(self, initial_url: str, redirect_url: str, final_response: DummyResponse):
        self.initial_url = initial_url
        self.redirect_url = redirect_url
        self.final_response = final_response
        self.follow_redirects = False
        self.requested_urls: list[str] = []
        self._responses = [
            DummyResponse(b"", status_code=302, headers={"Location": redirect_url}),
            final_response,
        ]

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url: str):
        self.requested_urls.append(url)
        response = self._responses.pop(0)
        if response.status_code == 302 and self.follow_redirects:
            location = response.headers["Location"]
            return await self.get(location)
        return response


def test_fetch_image_handles_extremely_thin_image(monkeypatch):
    buf = BytesIO()
    Image.new("RGB", (1, 1000), color="white").save(buf, format="JPEG")
    response = DummyResponse(buf.getvalue())

    monkeypatch.setattr(
        server.httpx,
        "AsyncClient",
        lambda *args, **kwargs: DummyAsyncClient(response),
    )

    result = asyncio.run(
        server.fetch_image_as_base64("http://example.com/image.jpg", max_side=100)
    )

    assert isinstance(result, str)
    assert len(result) > 0


def test_fetch_image_single_pixel_width_does_not_raise_value_error(monkeypatch):
    buf = BytesIO()
    Image.new("RGB", (1, 512), color="white").save(buf, format="JPEG")
    response = DummyResponse(buf.getvalue())

    monkeypatch.setattr(
        server.httpx,
        "AsyncClient",
        lambda *args, **kwargs: DummyAsyncClient(response),
    )

    try:
        result = asyncio.run(
            server.fetch_image_as_base64("http://example.com/tiny.jpg", max_side=64)
        )
    except ValueError as exc:  # pragma: no cover - explicit failure path for clarity
        pytest.fail(f"Unexpected ValueError during resize: {exc}")

    assert isinstance(result, str)
    assert result


def test_fetch_image_follows_redirect_and_returns_final_content(monkeypatch):
    initial_url = "http://example.com/start.jpg"
    redirect_url = "http://cdn.example.com/final.jpg"
    final_payload = b"redirected-bytes"
    final_response = DummyResponse(final_payload)
    redirect_client = DummyRedirectAsyncClient(initial_url, redirect_url, final_response)

    def client_factory(*args, **kwargs):
        redirect_client.follow_redirects = kwargs.get("follow_redirects", False)
        assert redirect_client.follow_redirects is True
        return redirect_client

    monkeypatch.setattr(server.httpx, "AsyncClient", client_factory)

    result = asyncio.run(server.fetch_image_as_base64(initial_url, max_side=128))

    assert redirect_client.requested_urls == [initial_url, redirect_url]
    assert base64.b64decode(result) == final_payload
