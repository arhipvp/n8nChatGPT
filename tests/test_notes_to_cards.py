from __future__ import annotations

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

from anki_mcp import NotesToCardsArgs, NotesToCardsResponse
from anki_mcp.tools.notes import notes_to_cards


def test_notes_to_cards_normalizes_response(monkeypatch):
    async def fake_anki_call(action, params):
        assert action == "notesToCards"
        assert params == {"notes": [101, 202]}
        return {"101": ["301", 302], 202: None}

    monkeypatch.setattr("anki_mcp.services.client.anki_call", fake_anki_call)

    notes_to_cards_fn = getattr(notes_to_cards, "fn", notes_to_cards)
    result = asyncio.run(notes_to_cards_fn({"noteIds": ["101", 202]}))

    assert isinstance(result, NotesToCardsResponse)
    assert result.notes_to_cards == {101: [301, 302], 202: []}
    payload = result.model_dump(by_alias=True)
    assert payload == {"notesToCards": {101: [301, 302], 202: []}}


def test_notes_to_cards_invalid_response(monkeypatch):
    async def fake_anki_call(action, params):
        return "unexpected"

    monkeypatch.setattr("anki_mcp.services.client.anki_call", fake_anki_call)

    notes_to_cards_fn = getattr(notes_to_cards, "fn", notes_to_cards)

    with pytest.raises(ValueError):
        asyncio.run(notes_to_cards_fn(NotesToCardsArgs(note_ids=[123])))

