import importlib
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import server


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _restore_env(original_deck, original_model):
    if original_deck is None:
        os.environ.pop("ANKI_DEFAULT_DECK", None)
    else:
        os.environ["ANKI_DEFAULT_DECK"] = original_deck

    if original_model is None:
        os.environ.pop("ANKI_DEFAULT_MODEL", None)
    else:
        os.environ["ANKI_DEFAULT_MODEL"] = original_model


def test_env_defaults_fallback_when_blank():
    original_deck = os.environ.get("ANKI_DEFAULT_DECK")
    original_model = os.environ.get("ANKI_DEFAULT_MODEL")

    try:
        os.environ["ANKI_DEFAULT_DECK"] = ""
        os.environ["ANKI_DEFAULT_MODEL"] = "   "
        module = importlib.reload(server)

        assert module.DEFAULT_DECK == "Default"
        assert module.DEFAULT_MODEL == "Поля для ChatGPT"
    finally:
        _restore_env(original_deck, original_model)
        importlib.reload(server)


def test_package_exports_follow_reload():
    import anki_mcp

    original_deck = os.environ.get("ANKI_DEFAULT_DECK")
    original_model = os.environ.get("ANKI_DEFAULT_MODEL")

    try:
        os.environ["ANKI_DEFAULT_DECK"] = "PackageDeck"
        os.environ["ANKI_DEFAULT_MODEL"] = "PackageModel"
        anki_mcp.config.reload_from_env()

        assert anki_mcp.DEFAULT_DECK == "PackageDeck"
        assert anki_mcp.DEFAULT_MODEL == "PackageModel"
    finally:
        _restore_env(original_deck, original_model)
        anki_mcp.config.reload_from_env()


@pytest.mark.anyio
async def test_manifest_environment_contains_defaults():
    original_deck = os.environ.get("ANKI_DEFAULT_DECK")
    original_model = os.environ.get("ANKI_DEFAULT_MODEL")

    try:
        os.environ["ANKI_DEFAULT_DECK"] = "DeckFromEnv"
        os.environ["ANKI_DEFAULT_MODEL"] = "ModelFromEnv"
        module = importlib.reload(server)

        # Сбросим форматтер fastmcp, чтобы гарантированно использовать нормализацию.
        module._format_mcp_info = None

        manifest = await module._build_manifest()
        assert manifest["environment"]["defaultDeck"] == "DeckFromEnv"
        assert manifest["environment"]["defaultModel"] == "ModelFromEnv"
    finally:
        _restore_env(original_deck, original_model)
        importlib.reload(server)


@pytest.mark.anyio
async def test_add_tools_follow_reloaded_defaults(monkeypatch):
    original_deck = os.environ.get("ANKI_DEFAULT_DECK")
    original_model = os.environ.get("ANKI_DEFAULT_MODEL")

    try:
        os.environ["ANKI_DEFAULT_DECK"] = "ReloadDeck"
        os.environ["ANKI_DEFAULT_MODEL"] = "ReloadModel"
        module = importlib.reload(server)

        async def fake_get_model_field_names(model_name):
            assert model_name == "ReloadModel"
            return ["Front", "Back"]

        monkeypatch.setattr(
            "anki_mcp.services.anki.get_model_field_names",
            fake_get_model_field_names,
        )

        captured_from_model = []

        async def fake_anki_call_model(action, params):
            captured_from_model.append((action, params))
            if action == "createDeck":
                return None
            if action == "addNotes":
                return [111]
            raise AssertionError(f"Unexpected action for add_from_model: {action}")

        monkeypatch.setattr(
            "anki_mcp.services.anki.anki_call", fake_anki_call_model
        )

        note = module.NoteInput(Front="Q", Back="A")
        result_from_model = await module.add_from_model.fn(items=[note])
        assert result_from_model.added == 1

        add_from_model_payload = next(
            params for action, params in captured_from_model if action == "addNotes"
        )
        note_payload = add_from_model_payload["notes"][0]
        assert note_payload["deckName"] == "ReloadDeck"
        assert note_payload["modelName"] == "ReloadModel"

        captured_add_notes = []

        async def fake_anki_call_notes(action, params):
            captured_add_notes.append((action, params))
            if action == "createDeck":
                return None
            if action == "addNotes":
                return [222]
            raise AssertionError(f"Unexpected action for add_notes: {action}")

        monkeypatch.setattr(
            "anki_mcp.services.anki.anki_call", fake_anki_call_notes
        )

        second_note = module.NoteInput(Front="Q2", Back="A2")
        args = module.AddNotesArgs(notes=[second_note])
        assert args.deck == "ReloadDeck"
        assert args.model == "ReloadModel"

        result_add_notes = await module.add_notes.fn(args)
        assert result_add_notes.added == 1

        add_notes_payload = next(
            params for action, params in captured_add_notes if action == "addNotes"
        )
        second_note_payload = add_notes_payload["notes"][0]
        assert second_note_payload["deckName"] == "ReloadDeck"
        assert second_note_payload["modelName"] == "ReloadModel"
    finally:
        _restore_env(original_deck, original_model)
        importlib.reload(server)
