import sys
import types
from collections import Counter
from pathlib import Path
from typing import List

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
                if scope.get("type") != "http":
                    raise RuntimeError("Only HTTP scope is supported")

                path = scope.get("path", "")
                method = scope.get("method", "GET").upper()
                if method == "GET" and path in {"/", "/.well-known/mcp.json"}:
                    from server import _manifest_response  # local import to avoid circular dependency

                    response = await _manifest_response()
                    await response(scope, receive, send)
                    return

                headers = [(b"content-type", b"application/json")]
                status = 404 if method == "GET" else 405
                body = b"{}"
                await send({
                    "type": "http.response.start",
                    "status": status,
                    "headers": headers,
                })
                await send({"type": "http.response.body", "body": body, "more_body": False})

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
async def test_add_from_model_unknown_fields_raise(monkeypatch):
    field_calls = Counter()

    async def fake_anki_call(action, params):
        if action == "createDeck":
            return None
        if action == "modelFieldNames":
            field_calls[params["modelName"]] += 1
            return ["Front", "Back"]
        if action == "modelTemplates":
            raise AssertionError("modelTemplates should not be called")
        if action == "modelStyling":
            raise AssertionError("modelStyling should not be called")
        raise AssertionError(f"Unexpected action: {action}")

    monkeypatch.setattr("server.anki_call", fake_anki_call)

    note = NoteInput(fields={"Question": "What is new?"})

    with pytest.raises(ValueError) as exc:
        await add_from_model.fn(deck="Deck", model="Basic", items=[note])

    message = str(exc.value)
    assert "Unknown note fields" in message
    assert "'Question'" in message
    assert "'Front'" in message and "'Back'" in message
    assert field_calls == Counter({"Basic": 1})


@pytest.mark.anyio
async def test_add_from_model_accepts_flat_fields(monkeypatch):
    captured_notes = {}
    field_calls = Counter()

    async def fake_anki_call(action, params):
        nonlocal captured_notes
        if action == "createDeck":
            return None
        if action == "modelFieldNames":
            field_calls[params["modelName"]] += 1
            return ["Front", "Back"]
        if action == "addNotes":
            captured_notes = params
            return [555]
        if action == "modelTemplates":
            raise AssertionError("modelTemplates should not be called")
        if action == "modelStyling":
            raise AssertionError("modelStyling should not be called")
        raise AssertionError(f"Unexpected action: {action}")

    monkeypatch.setattr("server.anki_call", fake_anki_call)

    items = [NoteInput(Front="Question?", Back="Answer!")]

    result = await add_from_model.fn(deck="Deck", model="Basic", items=items)

    assert result.added == 1
    assert captured_notes["notes"][0]["fields"] == {"Front": "Question?", "Back": "Answer!"}
    assert captured_notes["notes"][0]["tags"] == []
    assert field_calls == Counter({"Basic": 1})


@pytest.mark.anyio
async def test_add_from_model_accepts_plain_dict(monkeypatch):
    captured_notes = {}
    field_calls = Counter()

    async def fake_anki_call(action, params):
        nonlocal captured_notes
        if action == "createDeck":
            return None
        if action == "modelFieldNames":
            field_calls[params["modelName"]] += 1
            return ["Front", "Back"]
        if action == "addNotes":
            captured_notes = params
            return [888]
        if action == "modelTemplates":
            raise AssertionError("modelTemplates should not be called")
        if action == "modelStyling":
            raise AssertionError("modelStyling should not be called")
        raise AssertionError(f"Unexpected action: {action}")

    monkeypatch.setattr("server.anki_call", fake_anki_call)

    result = await add_from_model.fn(
        deck="Deck",
        model="Basic",
        items=[{"Front": "Q", "Back": "A", "tags": "auto"}],
    )

    assert result.added == 1
    assert captured_notes["notes"][0]["fields"] == {"Front": "Q", "Back": "A"}
    assert captured_notes["notes"][0]["tags"] == ["auto"]
    assert field_calls == Counter({"Basic": 1})


@pytest.mark.anyio
async def test_add_from_model_normalizes_note_input_tags(monkeypatch):
    captured_notes = {}
    field_calls = Counter()

    async def fake_anki_call(action, params):
        nonlocal captured_notes
        if action == "createDeck":
            return None
        if action == "modelFieldNames":
            field_calls[params["modelName"]] += 1
            return ["Front", "Back"]
        if action == "addNotes":
            captured_notes = params
            return [999]
        if action == "modelTemplates":
            raise AssertionError("modelTemplates should not be called")
        if action == "modelStyling":
            raise AssertionError("modelStyling should not be called")
        raise AssertionError(f"Unexpected action: {action}")

    monkeypatch.setattr("server.anki_call", fake_anki_call)

    note = NoteInput(Front="Q", Back="A", tags="auto")

    result = await add_from_model.fn(deck="Deck", model="Basic", items=[note])

    assert result.added == 1
    assert captured_notes["notes"][0]["tags"] == ["auto"]
    assert field_calls == Counter({"Basic": 1})


@pytest.mark.anyio
async def test_add_notes_accepts_flat_fields(monkeypatch):
    captured_notes = {}

    async def fake_anki_call(action, params):
        nonlocal captured_notes
        if action == "createDeck":
            return None
        if action == "modelFieldNames":
            return ["Front", "Back"]
        if action == "modelTemplates":
            raise AssertionError("modelTemplates should not be called for add_notes")
        if action == "modelStyling":
            raise AssertionError("modelStyling should not be called for add_notes")
        if action == "addNotes":
            captured_notes = params
            return [777]
        raise AssertionError(f"Unexpected action: {action}")

    monkeypatch.setattr("server.anki_call", fake_anki_call)

    args = AddNotesArgs(deck="Deck", model="Basic", notes=[{"Front": "Q", "Back": "A"}])

    result = await add_notes.fn(args)

    assert result.added == 1
    assert captured_notes["notes"][0]["fields"] == {"Front": "Q", "Back": "A"}
    assert captured_notes["notes"][0]["tags"] == []


@pytest.mark.anyio
async def test_add_from_model_respects_note_level_deck_and_model(monkeypatch):
    captured_notes = {}
    create_calls: List[str] = []
    requested_models: List[str] = []
    field_calls = Counter()

    fields_by_model = {
        "Basic": ["Front", "Back"],
        "Cloze": ["Text", "Extra"],
    }

    async def fake_anki_call(action, params):
        nonlocal captured_notes
        if action == "createDeck":
            create_calls.append(params["deck"])
            return None
        if action == "modelFieldNames":
            model_name = params["modelName"]
            requested_models.append(model_name)
            field_calls[model_name] += 1
            return fields_by_model[model_name]
        if action == "addNotes":
            captured_notes = params
            return [111, 222]
        if action == "modelTemplates":
            raise AssertionError("modelTemplates should not be called")
        if action == "modelStyling":
            raise AssertionError("modelStyling should not be called")
        raise AssertionError(f"Unexpected action: {action}")

    monkeypatch.setattr("server.anki_call", fake_anki_call)

    default_note = NoteInput(Front="Q1", Back="A1")
    override_note = NoteInput(
        fields={"Text": "cloze", "Extra": "info"},
        deckName="Special Deck",
        modelName="Cloze",
    )

    result = await add_from_model.fn(
        deck="Deck",
        model="Basic",
        items=[default_note, override_note],
    )

    assert result.added == 2
    assert set(create_calls) == {"Deck", "Special Deck"}
    assert set(requested_models) == {"Basic", "Cloze"}
    assert captured_notes["notes"][0]["deckName"] == "Deck"
    assert captured_notes["notes"][0]["modelName"] == "Basic"
    assert captured_notes["notes"][1]["deckName"] == "Special Deck"
    assert captured_notes["notes"][1]["modelName"] == "Cloze"
    assert "deckName" not in captured_notes["notes"][1]["fields"]
    assert "modelName" not in captured_notes["notes"][1]["fields"]
    assert field_calls == Counter({"Basic": 1, "Cloze": 1})


@pytest.mark.anyio
async def test_add_notes_respects_note_level_deck_and_model(monkeypatch):
    captured_notes = {}
    create_calls: List[str] = []
    requested_models: List[str] = []

    fields_by_model = {
        "Basic": ["Front", "Back"],
        "Cloze": ["Text", "Extra"],
    }

    async def fake_anki_call(action, params):
        nonlocal captured_notes
        if action == "createDeck":
            create_calls.append(params["deck"])
            return None
        if action == "modelFieldNames":
            model_name = params["modelName"]
            requested_models.append(model_name)
            return fields_by_model[model_name]
        if action == "modelTemplates":
            raise AssertionError("modelTemplates should not be called for add_notes")
        if action == "modelStyling":
            raise AssertionError("modelStyling should not be called for add_notes")
        if action == "addNotes":
            captured_notes = params
            return [333, 444]
        raise AssertionError(f"Unexpected action: {action}")

    monkeypatch.setattr("server.anki_call", fake_anki_call)

    args = AddNotesArgs(
        deck="Deck",
        model="Basic",
        notes=[
            {"Front": "Q1", "Back": "A1"},
            {
                "Text": "cloze",
                "Extra": "info",
                "deckName": "Special Deck",
                "modelName": "Cloze",
            },
        ],
    )

    result = await add_notes.fn(args)

    assert result.added == 2
    assert set(create_calls) == {"Deck", "Special Deck"}
    assert set(requested_models) == {"Basic", "Cloze"}
    assert captured_notes["notes"][0]["deckName"] == "Deck"
    assert captured_notes["notes"][0]["modelName"] == "Basic"
    assert captured_notes["notes"][1]["deckName"] == "Special Deck"
    assert captured_notes["notes"][1]["modelName"] == "Cloze"
    assert "deckName" not in captured_notes["notes"][1]["fields"]
    assert "modelName" not in captured_notes["notes"][1]["fields"]


def test_note_input_requires_fields_or_flat_data():
    with pytest.raises(ValueError) as exc:
        AddNotesArgs(deck="Deck", model="Basic", notes=[{}])

    assert "Каждый элемент items должен содержать объект fields" in str(exc.value)
