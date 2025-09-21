import asyncio
import sys
import types
from pathlib import Path

import pytest

try:  # pragma: no cover - executed only when dependency missing
    import fastmcp as _fastmcp_mod  # type: ignore  # noqa: F401
except ModuleNotFoundError:  # pragma: no cover - fallback for minimal envs
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

        def custom_route(self, *args, **kwargs):
            return self.tool(*args, **kwargs)

        def http_app(self):  # pragma: no cover - not used in tests
            async def _app(scope, receive, send):
                raise RuntimeError("HTTP app is not available in tests")

            return _app

    sys.modules.setdefault("fastmcp", types.ModuleType("fastmcp")).FastMCP = _FakeFastMCP


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server import (  # noqa: E402
    ListTagsResponse,
    list_tags,
)


def _unwrap_tool(func):
    return getattr(func, "fn", func)


def test_list_tags_normalizes_and_sorts(monkeypatch):
    calls = []

    async def fake_anki_call(action, params):
        calls.append((action, params))
        assert action == "getTags"
        assert params == {}
        return [" travel ", "English", "Pronunciation", "english", "Travel"]

    monkeypatch.setattr("anki_mcp.services.anki.anki_call", fake_anki_call)

    list_tags_fn = _unwrap_tool(list_tags)
    result = asyncio.run(list_tags_fn())

    assert isinstance(result, ListTagsResponse)
    assert result.tags == ["English", "Pronunciation", "travel"]
    assert calls == [("getTags", {})]


def test_list_tags_invalid_payload(monkeypatch):
    async def fake_anki_call(action, params):
        assert action == "getTags"
        assert params == {}
        return {"not": "a list"}

    monkeypatch.setattr("anki_mcp.services.anki.anki_call", fake_anki_call)

    list_tags_fn = _unwrap_tool(list_tags)

    with pytest.raises(ValueError, match="sequence of strings"):
        asyncio.run(list_tags_fn())
