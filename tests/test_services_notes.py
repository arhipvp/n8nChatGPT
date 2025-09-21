import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from anki_mcp.schemas import NoteInfo
from anki_mcp.services import notes


def test_normalize_fields_for_model_matches_case_insensitive():
    normalized, matched, unknown = notes.normalize_fields_for_model(
        {"front": "Question", "Extra": ""}, ["Front", "Back"]
    )
    assert normalized == {"Front": "Question", "Back": ""}
    assert matched == 1
    assert unknown == ["Extra"]


def test_normalize_and_validate_note_fields_requires_primary():
    with pytest.raises(ValueError):
        notes.normalize_and_validate_note_fields({}, ["Front", "Back"])


def test_normalize_notes_info_converts_entries():
    raw_notes = [
        {
            "noteId": "123",
            "modelName": "Basic",
            "deckName": "Default",
            "tags": ["tag1", ""],
            "fields": {"Front": {"value": "Hello"}, "Back": None},
            "cards": ["10", 11],
        }
    ]

    normalized = notes.normalize_notes_info(raw_notes)

    assert len(normalized) == 1
    note = normalized[0]
    assert isinstance(note, NoteInfo)
    assert note.note_id == 123
    assert note.fields == {"Front": "Hello", "Back": ""}
    assert note.cards == [10, 11]


def test_normalize_notes_info_rejects_non_list():
    with pytest.raises(ValueError):
        notes.normalize_notes_info({})
