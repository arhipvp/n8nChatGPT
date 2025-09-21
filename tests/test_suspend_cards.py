import asyncio
import sys
import types
from pathlib import Path

import pytest


def _field_stub(*args, **kwargs):  # pragma: no cover - support for missing pydantic
    if "default" in kwargs:
        return kwargs["default"]
    if "default_factory" in kwargs:
        return kwargs["default_factory"]()
    return None


try:  # pragma: no cover - exercised only when dependency missing
    import fastmcp as _fastmcp_mod  # type: ignore  # noqa: F401
except ModuleNotFoundError:  # pragma: no cover - executed in minimal test environments
    class _FakeFastMCP:
        def __init__(self, *args, **kwargs):
            pass

        def tool(self, *args, **kwargs):
            def decorator(func):
                return func

            return decorator

        def custom_route(self, *args, **kwargs):
            return self.tool(*args, **kwargs)

        def http_app(self):  # minimal shim for tests needing HTTP app
            import types as _types

            async def _noop_app(scope, receive, send):  # pragma: no cover
                raise RuntimeError("ASGI app not available in tests")

            return _types.SimpleNamespace(__call__=_noop_app)

    sys.modules.setdefault("fastmcp", types.ModuleType("fastmcp")).FastMCP = _FakeFastMCP


try:  # pragma: no cover - exercised only when dependency missing
    import pydantic as _pydantic_mod  # type: ignore  # noqa: F401
except ModuleNotFoundError:  # pragma: no cover - executed in minimal test environments
    pydantic_stub = types.SimpleNamespace(
        BaseModel=object,
        Field=_field_stub,
        constr=lambda **kwargs: str,
        AnyHttpUrl=str,
        ConfigDict=None,
    )
    sys.modules.setdefault("pydantic", pydantic_stub)


try:  # pragma: no cover - exercised only when dependency missing
    from PIL import Image as _pil_image  # type: ignore  # noqa: F401
except ModuleNotFoundError:  # pragma: no cover - executed in minimal test environments
    image_module = types.ModuleType("Image")

    def _unavailable(*args, **kwargs):  # pragma: no cover - helper for degraded envs
        raise RuntimeError("Pillow is not available in this environment")

    image_module.open = _unavailable  # type: ignore[attr-defined]
    pil_module = types.ModuleType("PIL")
    pil_module.Image = image_module  # type: ignore[attr-defined]
    sys.modules.setdefault("PIL", pil_module)
    sys.modules.setdefault("PIL.Image", image_module)


try:  # pragma: no cover - exercised only when dependency missing
    import httpx as _httpx_mod  # type: ignore  # noqa: F401
except ModuleNotFoundError:  # pragma: no cover - executed in minimal test environments
    class _DummyAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):  # pragma: no cover - should not be used in tests
            raise RuntimeError("httpx AsyncClient is not available")

        async def __aexit__(self, exc_type, exc, tb):  # pragma: no cover
            return False

    httpx_stub = types.SimpleNamespace(AsyncClient=_DummyAsyncClient)
    sys.modules.setdefault("httpx", httpx_stub)


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server import CardIdsArgs, suspend_cards, unsuspend_cards


def _run_tool(func, args):
    tool_fn = getattr(func, "fn", func)
    return asyncio.run(tool_fn(args))


def test_suspend_cards_normalizes_payload(monkeypatch):
    captured = {}

    async def fake_anki_call(action, params):
        captured["action"] = action
        captured["params"] = params
        return None

    monkeypatch.setattr("anki_mcp.services.anki.anki_call", fake_anki_call)

    result = _run_tool(suspend_cards, {"cardIds": ["101", 202]})

    assert captured["action"] == "suspendCards"
    assert captured["params"] == {"cards": [101, 202]}
    assert result == {"card_ids": [101, 202], "suspended": True, "anki_response": None}


def test_unsuspend_cards_accepts_schema(monkeypatch):
    captured = {}

    async def fake_anki_call(action, params):
        captured["action"] = action
        captured["params"] = params
        return {"result": "ok"}

    monkeypatch.setattr("anki_mcp.services.anki.anki_call", fake_anki_call)

    result = _run_tool(unsuspend_cards, CardIdsArgs(card_ids=[333]))

    assert captured["action"] == "unsuspendCards"
    assert captured["params"] == {"cards": [333]}
    assert result == {
        "card_ids": [333],
        "suspended": False,
        "anki_response": {"result": "ok"},
    }


def test_suspend_cards_rejects_invalid_ids(monkeypatch):
    called = False

    async def fake_anki_call(action, params):  # pragma: no cover - should not run
        nonlocal called
        called = True
        return None

    monkeypatch.setattr("anki_mcp.services.anki.anki_call", fake_anki_call)

    with pytest.raises(ValueError):
        _run_tool(suspend_cards, {"cardIds": [True]})

    assert called is False


def test_suspend_cards_wraps_runtime_error(monkeypatch):
    async def fake_anki_call(action, params):
        raise RuntimeError("Anki error: sample failure")

    monkeypatch.setattr("anki_mcp.services.anki.anki_call", fake_anki_call)

    with pytest.raises(RuntimeError) as excinfo:
        _run_tool(suspend_cards, {"cardIds": [555]})

    assert "Не удалось скрыть карточки Anki" in str(excinfo.value)
    assert "sample failure" in str(excinfo.value)
