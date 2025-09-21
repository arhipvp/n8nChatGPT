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

        def custom_route(self, *args, **kwargs):  # pragma: no cover - для совместимости
            return self.tool(*args, **kwargs)

        def http_app(self):  # pragma: no cover - не используется в тестах
            async def _app(scope, receive, send):
                raise RuntimeError("HTTP app недоступно в тестовом окружении")

            return _app

    sys.modules.setdefault("fastmcp", types.ModuleType("fastmcp")).FastMCP = _FakeFastMCP


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server import sync  # noqa: E402


def _unwrap(tool):
    return getattr(tool, "fn", tool)


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_sync_invokes_rpc_and_normalizes_none(monkeypatch):
    calls = []

    async def fake_anki_call(action, params):
        calls.append((action, params))
        return None

    monkeypatch.setattr("anki_mcp.services.client.anki_call", fake_anki_call)

    result = await _unwrap(sync)()

    assert result == {"synced": True}
    assert calls == [("sync", {})]


@pytest.mark.anyio
async def test_sync_wraps_boolean_result(monkeypatch):
    async def fake_anki_call(action, params):
        assert action == "sync"
        assert params == {}
        return False

    monkeypatch.setattr("anki_mcp.services.client.anki_call", fake_anki_call)

    result = await _unwrap(sync)()

    assert result == {"synced": False}


@pytest.mark.anyio
async def test_sync_converts_invalid_params_error(monkeypatch):
    async def fake_anki_call(action, params):
        raise RuntimeError("Anki error: invalid auth token")

    monkeypatch.setattr("anki_mcp.services.client.anki_call", fake_anki_call)

    with pytest.raises(ValueError, match="invalid auth token"):
        await _unwrap(sync)()


@pytest.mark.anyio
async def test_sync_preserves_system_errors(monkeypatch):
    async def fake_anki_call(action, params):
        raise RuntimeError("Anki error: collection is locked")

    monkeypatch.setattr("anki_mcp.services.client.anki_call", fake_anki_call)

    with pytest.raises(RuntimeError, match="collection is locked"):
        await _unwrap(sync)()

