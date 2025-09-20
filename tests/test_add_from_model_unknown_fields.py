import sys
import types
from pathlib import Path

import pytest


try:  # pragma: no cover - exercised only when dependency missing
    import fastmcp as _fastmcp_mod  # type: ignore
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


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server import NoteInput, add_from_model


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_add_from_model_unknown_fields_raise(monkeypatch):
    async def fake_anki_call(action, params):
        if action == "createDeck":
            return None
        if action == "modelFieldNames":
            return ["Front", "Back"]
        if action == "modelTemplates":
            return {}
        if action == "modelStyling":
            return {"css": ""}
        raise AssertionError(f"Unexpected action: {action}")

    monkeypatch.setattr("server.anki_call", fake_anki_call)

    note = NoteInput(fields={"Question": "What is new?"})

    with pytest.raises(ValueError) as exc:
        await add_from_model.fn(deck="Deck", model="Basic", items=[note])

    message = str(exc.value)
    assert "Unknown note fields" in message
    assert "'Question'" in message
    assert "'Front'" in message and "'Back'" in message
