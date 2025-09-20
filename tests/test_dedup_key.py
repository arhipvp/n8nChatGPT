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

from server import AddNotesArgs, NoteInput, add_from_model, add_notes


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_add_from_model_includes_dedup_key(monkeypatch):
    async def fake_anki_call(action, params):
        if action == "createDeck":
            return None
        if action == "modelFieldNames":
            return ["Front", "Back"]
        if action == "modelTemplates":
            return {}
        if action == "modelStyling":
            return {"css": ""}
        if action == "addNotes":
            return [101, None]
        raise AssertionError(f"Unexpected action: {action}")

    monkeypatch.setattr("server.anki_call", fake_anki_call)

    items = [
        NoteInput(fields={"Front": "Q1", "Back": "A1"}, dedup_key="first"),
        NoteInput(fields={"Front": "Q2", "Back": "A2"}, dedup_key="second"),
    ]

    result = await add_from_model.fn(deck="Deck", model="Basic", items=items)

    assert result.added == 1
    assert result.skipped == 1
    assert result.details[0]["status"] == "ok"
    assert result.details[0]["dedup_key"] == "first"
    assert result.details[1]["status"] == "duplicate"
    assert result.details[1]["dedup_key"] == "second"


@pytest.mark.anyio
async def test_add_notes_includes_dedup_key(monkeypatch):
    async def fake_anki_call(action, params):
        if action == "createDeck":
            return None
        if action == "modelFieldNames":
            return ["Front", "Back"]
        if action == "modelTemplates":
            raise AssertionError("modelTemplates should not be called for add_notes")
        if action == "modelStyling":
            raise AssertionError("modelStyling should not be called for add_notes")
        if action == "addNotes":
            return [202, None]
        raise AssertionError(f"Unexpected action: {action}")

    monkeypatch.setattr("server.anki_call", fake_anki_call)

    args = AddNotesArgs(
        deck="Deck",
        model="Basic",
        notes=[
            NoteInput(fields={"Front": "Q1"}, dedup_key="alpha"),
            NoteInput(fields={"Front": "Q2"}, dedup_key="beta"),
        ],
    )

    result = await add_notes.fn(args)

    assert result.added == 1
    assert result.skipped == 1
    assert result.details[0]["status"] == "ok"
    assert result.details[0]["dedup_key"] == "alpha"
    assert result.details[1]["status"] == "duplicate"
    assert result.details[1]["dedup_key"] == "beta"


@pytest.mark.anyio
async def test_add_notes_lowercase_fields_empty_front(monkeypatch):
    async def fake_anki_call(action, params):
        if action == "createDeck":
            return None
        if action == "modelFieldNames":
            return ["Front", "Back"]
        if action == "modelTemplates":
            raise AssertionError("modelTemplates should not be called for add_notes")
        if action == "modelStyling":
            raise AssertionError("modelStyling should not be called for add_notes")
        if action == "addNotes":
            raise AssertionError("addNotes should not be called when fields invalid")
        raise AssertionError(f"Unexpected action: {action}")

    monkeypatch.setattr("server.anki_call", fake_anki_call)

    args = AddNotesArgs(
        deck="Deck",
        model="Basic",
        notes=[NoteInput(fields={"front": "", "back": "Answer"})],
    )

    with pytest.raises(ValueError) as exc:
        await add_notes.fn(args)

    message = str(exc.value)
    assert "Ensure required field 'Front' is provided." in message
    assert "note is empty" not in message.lower()
