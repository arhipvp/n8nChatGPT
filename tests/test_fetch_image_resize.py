import asyncio
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

    result = asyncio.run(
        server.fetch_image_as_base64("http://example.com/image.jpg", max_side=100)
    )

    assert isinstance(result, str)
    assert len(result) > 0
