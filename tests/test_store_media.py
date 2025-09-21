import base64
import sys
import types
from pathlib import Path

import pytest

try:  # pragma: no cover - используется только при отсутствии зависимости
    import fastmcp as _fastmcp_mod  # type: ignore  # noqa: F401
except ModuleNotFoundError:  # pragma: no cover - минимальные заглушки для тестовой среды
    class _FakeToolWrapper:
        def __init__(self, func):
            self.fn = func

        def __call__(self, *args, **kwargs):
            return self.fn(*args, **kwargs)

    class _FakeFastMCP:
        def __init__(self, *args, **kwargs):
            pass

        def tool(self, *args, **kwargs):
            def decorator(func):
                return _FakeToolWrapper(func)

            return decorator

        def custom_route(self, *args, **kwargs):  # pragma: no cover - не используется здесь
            return self.tool(*args, **kwargs)

        def http_app(self):  # pragma: no cover - для совместимости с другими тестами
            async def _app(scope, receive, send):
                raise RuntimeError("HTTP app недоступно в тестовом окружении")

            return _app

    sys.modules.setdefault("fastmcp", types.ModuleType("fastmcp")).FastMCP = _FakeFastMCP


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server import StoreMediaArgs, store_media  # noqa: E402


def _unwrap(tool):
    return getattr(tool, "fn", tool)


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_store_media_accepts_aliases(monkeypatch):
    encoded = base64.b64encode(b"sample bytes").decode("ascii")
    calls = {}

    async def fake_store_media_file(filename: str, data_b64: str):
        calls["filename"] = filename
        calls["data"] = data_b64
        return {"stored": True}

    monkeypatch.setattr(
        "anki_mcp.services.client.store_media_file", fake_store_media_file
    )

    args = {"filename": "audio/test.mp3", "data": encoded}

    result = await _unwrap(store_media)(args)

    assert result == {"filename": "audio/test.mp3", "anki_response": {"stored": True}}
    assert calls == {"filename": "audio/test.mp3", "data": encoded}


@pytest.mark.anyio
async def test_store_media_rejects_invalid_base64(monkeypatch):
    async def fail_store_media_file(*args, **kwargs):  # pragma: no cover - защита от вызова
        pytest.fail("store_media_file не должен вызываться для некорректного Base64")

    monkeypatch.setattr(
        "anki_mcp.services.client.store_media_file", fail_store_media_file
    )

    with pytest.raises(ValueError):
        await _unwrap(store_media)(
            StoreMediaArgs(filename="bad.bin", data_base64="not base64?!")
        )


@pytest.mark.anyio
async def test_store_media_propagates_service_errors(monkeypatch):
    encoded = base64.b64encode(b"broken").decode("ascii")

    async def fake_store_media_file(filename: str, data_b64: str):
        raise RuntimeError("AnkiConnect unavailable")

    monkeypatch.setattr(
        "anki_mcp.services.client.store_media_file", fake_store_media_file
    )

    with pytest.raises(RuntimeError):
        await _unwrap(store_media)(
            StoreMediaArgs(filename="broken.wav", data_base64=encoded)
        )
