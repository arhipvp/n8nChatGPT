import sys
import types
from pathlib import Path

import pytest


try:  # pragma: no cover - exercised only when dependency missing
    import fastmcp as _fastmcp_mod  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - executed in minimal test environments
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

        def http_app(self):  # minimal shim for tests needing HTTP app
            async def _app(scope, receive, send):  # pragma: no cover - exercised in manifest tests
                raise RuntimeError("ASGI app not available in tests")

            return _app

    sys.modules.setdefault("fastmcp", types.ModuleType("fastmcp")).FastMCP = _FakeFastMCP


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server import AddNotesArgs, NoteInput, add_from_model, add_notes


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_add_from_model_autolinks_sources(monkeypatch):
    captured_notes = {}

    async def fake_anki_call(action, params):
        nonlocal captured_notes
        if action == "createDeck":
            return None
        if action == "modelFieldNames":
            return ["Front", "Back", "Sources"]
        if action == "addNotes":
            captured_notes = params
            return [321]
        raise AssertionError(f"Unexpected action: {action}")

    monkeypatch.setattr("anki_mcp.services.anki.anki_call", fake_anki_call)

    note = NoteInput(fields={"Front": "Q", "Back": "A", "Sources": "https://example.com"})

    result = await add_from_model.fn(deck="Deck", model="Basic", items=[note])

    assert result.added == 1
    sources_value = captured_notes["notes"][0]["fields"]["Sources"]
    assert sources_value == '<a href="https://example.com">https://example.com</a>'


@pytest.mark.anyio
async def test_add_notes_autolinks_sources(monkeypatch):
    captured_notes = {}

    async def fake_anki_call(action, params):
        nonlocal captured_notes
        if action == "createDeck":
            return None
        if action == "modelFieldNames":
            return ["Front", "Back", "Sources"]
        if action == "addNotes":
            captured_notes = params
            return [654]
        raise AssertionError(f"Unexpected action: {action}")

    monkeypatch.setattr("anki_mcp.services.anki.anki_call", fake_anki_call)

    args = AddNotesArgs(
        deck="Deck",
        model="Basic",
        notes=[
            NoteInput(fields={"front": "Question", "sources": "https://example.org"}),
        ],
    )

    result = await add_notes.fn(args)

    assert result.added == 1
    sources_value = captured_notes["notes"][0]["fields"]["Sources"]
    assert sources_value == '<a href="https://example.org">https://example.org</a>'
