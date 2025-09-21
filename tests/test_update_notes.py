import sys
import types
from collections import Counter
from pathlib import Path

import pytest


try:  # pragma: no cover - exercised only when dependency missing
    import fastmcp as _fastmcp_mod  # type: ignore  # noqa: F401
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

        def http_app(self):  # pragma: no cover - exercised in manifest tests only
            async def _app(scope, receive, send):
                raise RuntimeError("HTTP app is not available in tests")

            return _app

    sys.modules.setdefault("fastmcp", types.ModuleType("fastmcp")).FastMCP = _FakeFastMCP


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server import (  # noqa: E402  # pylint: disable=wrong-import-position
    ImageSpec,
    NoteUpdate,
    UpdateNotesArgs,
    update_notes,
)


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _build_note_info(note_id=1, model="Basic", deck="Default"):
    return {
        "noteId": note_id,
        "modelName": model,
        "deckName": deck,
        "tags": [],
        "fields": {
            "Front": {"value": "Old front"},
            "Back": {"value": "Old back"},
        },
        "cards": [1001],
    }


@pytest.mark.anyio
async def test_update_notes_normalizes_fields_and_calls_actions(monkeypatch):
    calls = []
    normalize_args = []
    process_calls = Counter()

    async def fake_anki_call(action, params):
        calls.append((action, params))
        if action == "notesInfo":
            return [_build_note_info()]
        if action in {"updateNoteFields", "addTags", "removeTags", "changeDeck"}:
            return None
        raise AssertionError(f"Unexpected action: {action}")

    def fake_normalize(fields, model_fields):
        normalize_args.append((fields, list(model_fields)))
        normalized = {field: "" for field in model_fields}
        for key, value in fields.items():
            if key.lower() == "front".lower():
                normalized["Front"] = value
        return normalized, 1, []

    async def fake_process(fields, results, note_index):
        process_calls[note_index] += 1
        results.append({"index": note_index, "info": "processed"})

    monkeypatch.setattr("anki_mcp.services.client.anki_call", fake_anki_call)
    monkeypatch.setattr(
        "anki_mcp.services.notes.normalize_fields_for_model", fake_normalize
    )
    monkeypatch.setattr(
        "anki_mcp.services.media.process_data_urls_in_fields", fake_process
    )

    note = NoteUpdate(
        noteId=1,
        fields={"front": "New front"},
        addTags=["new"],
        removeTags=["old"],
        deck="Target",
    )
    args = UpdateNotesArgs(notes=[note])
    update_fn = getattr(update_notes, "fn", update_notes)
    result = await update_fn(args)

    assert result.updated == 1
    assert result.skipped == 0
    assert len(result.details) == 1
    detail = result.details[0]
    assert detail["status"] == "ok"
    assert detail.get("updatedFields") == ["Front"]
    assert detail.get("addedTags") == ["new"]
    assert detail.get("removedTags") == ["old"]
    assert detail.get("deckChangedTo") == "Target"
    assert process_calls[0] == 1
    assert normalize_args == [({"front": "New front"}, ["Front", "Back"])]
    assert [action for action, _ in calls] == [
        "notesInfo",
        "updateNoteFields",
        "addTags",
        "removeTags",
        "changeDeck",
    ]


@pytest.mark.anyio
async def test_update_notes_handles_images(monkeypatch):
    calls = []
    stored_files = []

    async def fake_anki_call(action, params):
        calls.append((action, params))
        if action == "notesInfo":
            return [_build_note_info()]
        if action == "updateNoteFields":
            return None
        raise AssertionError(f"Unexpected action: {action}")

    async def fake_store_media(filename, data_b64):
        stored_files.append((filename, data_b64))

    def fake_sanitize(payload):
        return "CLEAN", "png"

    monkeypatch.setattr("anki_mcp.services.client.anki_call", fake_anki_call)
    monkeypatch.setattr("anki_mcp.services.client.store_media_file", fake_store_media)
    monkeypatch.setattr(
        "anki_mcp.services.media.sanitize_image_payload", fake_sanitize
    )
    async def fake_process(fields, results, note_index):
        return None

    monkeypatch.setattr(
        "anki_mcp.services.media.process_data_urls_in_fields", fake_process
    )

    note = NoteUpdate(
        noteId=1,
        images=[
            ImageSpec(image_base64="dummy", target_field="Back", filename="img.png"),
        ],
    )
    args = UpdateNotesArgs(notes=[note])
    update_fn = getattr(update_notes, "fn", update_notes)
    result = await update_fn(args)

    assert stored_files == [("img.png", "CLEAN")]
    assert result.updated == 1
    assert [action for action, _ in calls] == ["notesInfo", "updateNoteFields"]
    fields_payload = calls[1][1]["note"]["fields"]
    assert "Back" in fields_payload
    assert "img.png" in fields_payload["Back"]
    detail = result.details[0]
    assert detail["status"] == "ok"
    assert detail.get("updatedFields") == ["Back"]
