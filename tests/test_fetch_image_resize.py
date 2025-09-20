import asyncio
import sys
import types
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image
import base64


def _field_stub(*args, **kwargs):
    if "default" in kwargs:
        return kwargs["default"]
    if "default_factory" in kwargs:
        return kwargs["default_factory"]()
    return None


fastmcp_stub = types.SimpleNamespace(
    FastMCP=lambda *args, **kwargs: types.SimpleNamespace(tool=lambda *a, **kw: (lambda f: f))
)
pydantic_stub = types.SimpleNamespace(
    BaseModel=object,
    Field=_field_stub,
    constr=lambda **kwargs: str,
    AnyHttpUrl=str,
)
sys.modules.setdefault("fastmcp", fastmcp_stub)
sys.modules.setdefault("pydantic", pydantic_stub)

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import server


class DummyResponse:
    def __init__(self, content: bytes):
        self.content = content

    def raise_for_status(self):
        return None


class DummyAsyncClient:
    def __init__(self, response: DummyResponse):
        self._response = response

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url: str):
        return self._response


def test_fetch_image_handles_extremely_thin_image(monkeypatch):
    buf = BytesIO()
    Image.new("RGB", (1, 1000), color="white").save(buf, format="JPEG")
    response = DummyResponse(buf.getvalue())

    monkeypatch.setattr(
        server.httpx,
        "AsyncClient",
        lambda *args, **kwargs: DummyAsyncClient(response),
    )

    result, fmt = asyncio.run(
        server.fetch_image_as_base64("http://example.com/image.jpg", max_side=100)
    )

    assert isinstance(result, str)
    assert fmt == "JPEG"
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
        result, fmt = asyncio.run(
            server.fetch_image_as_base64("http://example.com/tiny.jpg", max_side=64)
        )
    except ValueError as exc:  # pragma: no cover - explicit failure path for clarity
        pytest.fail(f"Unexpected ValueError during resize: {exc}")

    assert isinstance(result, str)
    assert fmt == "JPEG"
    assert result


def test_fetch_image_preserves_png_alpha(monkeypatch):
    buf = BytesIO()
    image = Image.new("RGBA", (10, 10), color=(255, 0, 0, 0))
    image.putpixel((0, 0), (10, 20, 30, 128))
    image.save(buf, format="PNG")
    response = DummyResponse(buf.getvalue())

    monkeypatch.setattr(
        server.httpx,
        "AsyncClient",
        lambda *args, **kwargs: DummyAsyncClient(response),
    )

    result, fmt = asyncio.run(
        server.fetch_image_as_base64("http://example.com/image.png", max_side=100)
    )

    assert fmt == "PNG"
    raw = base64.b64decode(result)
    assert raw.startswith(b"\x89PNG\r\n\x1a\n")

    with Image.open(BytesIO(raw)) as processed:
        assert "A" in processed.getbands()
