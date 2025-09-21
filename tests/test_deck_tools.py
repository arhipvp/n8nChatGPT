import asyncio
import sys
import types
from pathlib import Path


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
                raise RuntimeError("ASGI app не доступно в тестовой среде")

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

from anki_mcp import DeleteDecksArgs, DeckInfo, RenameDeckArgs
from anki_mcp.tools.decks import delete_decks, list_decks, rename_deck


def _unwrap_tool(func):
    return getattr(func, "fn", func)


def test_list_decks_normalizes_response(monkeypatch):
    calls = []

    async def fake_anki_call(action, params):
        calls.append((action, params))
        assert action == "deckNamesAndIds"
        assert params == {}
        return {"Default": 1, "Custom": "1700000000000"}

    monkeypatch.setattr("anki_mcp.services.client.anki_call", fake_anki_call)

    list_decks_fn = _unwrap_tool(list_decks)
    result = asyncio.run(list_decks_fn())

    assert isinstance(result, list)
    assert result == [DeckInfo(id=1, name="Default"), DeckInfo(id=1700000000000, name="Custom")]
    assert calls == [("deckNamesAndIds", {})]


def test_list_decks_handles_empty_mapping(monkeypatch):
    async def fake_anki_call(action, params):
        assert action == "deckNamesAndIds"
        assert params == {}
        return {}

    monkeypatch.setattr("anki_mcp.services.client.anki_call", fake_anki_call)

    list_decks_fn = _unwrap_tool(list_decks)
    result = asyncio.run(list_decks_fn())

    assert result == []


def test_rename_deck_payload(monkeypatch):
    calls = []

    async def fake_anki_call(action, params):
        calls.append((action, params))
        assert action == "renameDeck"
        assert params == {"oldName": "Inbox", "newName": "Archive"}
        return "ok"

    monkeypatch.setattr("anki_mcp.services.client.anki_call", fake_anki_call)

    rename_deck_fn = _unwrap_tool(rename_deck)
    args = RenameDeckArgs(old_name="Inbox", new_name="Archive")
    result = asyncio.run(rename_deck_fn(args))

    assert result == "ok"
    assert calls == [("renameDeck", {"oldName": "Inbox", "newName": "Archive"})]


def test_delete_decks_payload(monkeypatch):
    calls = []

    async def fake_anki_call(action, params):
        calls.append((action, params))
        assert action == "deleteDecks"
        assert params == {"decks": ["Inbox", "Temp"], "cardsToo": True}
        return None

    monkeypatch.setattr("anki_mcp.services.client.anki_call", fake_anki_call)

    delete_decks_fn = _unwrap_tool(delete_decks)
    args = DeleteDecksArgs(decks=["Inbox", "Temp"], cards_too=True)
    result = asyncio.run(delete_decks_fn(args))

    assert result is None
    assert calls == [("deleteDecks", {"decks": ["Inbox", "Temp"], "cardsToo": True})]
