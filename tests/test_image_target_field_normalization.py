import base64
import sys
import types
from types import SimpleNamespace
from pathlib import Path

import pytest


try:  # pragma: no cover - выполняется только при отсутствии зависимости
    import fastmcp as _fastmcp_mod  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - минимальный заглушечный MCP
    class _FakeFastMCP:
        def __init__(self, *args, **kwargs):
            pass

        def tool(self, *args, **kwargs):
            def decorator(func):
                return func

            return decorator

        def custom_route(self, *args, **kwargs):
            return self.tool(*args, **kwargs)

        def http_app(self):  # pragma: no cover - в тестах не вызывается
            async def _noop_app(scope, receive, send):
                raise RuntimeError("ASGI app not available in tests")

            return SimpleNamespace(__call__=_noop_app)

    sys.modules.setdefault("fastmcp", types.ModuleType("fastmcp")).FastMCP = _FakeFastMCP


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import server


@pytest.fixture
def anyio_backend():
    return "asyncio"


IMAGE_B64 = base64.b64encode(b"target-alias").decode("ascii")


def _setup_common_monkeypatches(monkeypatch, captured):
    async def fake_anki_call(action: str, params: dict):
        if action == "createDeck":
            captured["createDeck"] = params
            return True
        if action == "modelFieldNames":
            return ["Front", "Back"]
        if action == "modelTemplates":
            return {}
        if action == "modelStyling":
            return {"css": ""}
        if action == "addNotes":
            captured["addNotes"] = params
            return [777]
        raise AssertionError(f"Unexpected action: {action}")

    async def fake_store_media_file(filename: str, data_b64: str):
        captured.setdefault("storeMedia", []).append({"filename": filename, "data": data_b64})

    monkeypatch.setattr(server, "anki_call", fake_anki_call)
    monkeypatch.setattr(server, "store_media_file", fake_store_media_file)
    monkeypatch.setattr(server.uuid, "uuid4", lambda: SimpleNamespace(hex="img-alias"))


@pytest.mark.anyio
async def test_add_from_model_image_target_field_normalized(monkeypatch):
    captured: dict[str, object] = {}
    _setup_common_monkeypatches(monkeypatch, captured)

    note = server.NoteInput(
        fields={"Front": "Question"},
        images=[{"image_base64": IMAGE_B64, "target_field": "back"}],
    )

    result = await server.add_from_model.fn("Deck", "Basic", [note])

    assert result.added == 1
    assert not any(detail.get("warn") == "unknown_target_field" for detail in result.details)

    add_notes_payload = captured.get("addNotes")
    assert isinstance(add_notes_payload, dict)
    fields = add_notes_payload["notes"][0]["fields"]
    assert "<img src=\"img-alias.jpg\"" in fields.get("Back", "")


@pytest.mark.anyio
async def test_add_from_model_unknown_target_field_warn(monkeypatch):
    captured: dict[str, object] = {}
    _setup_common_monkeypatches(monkeypatch, captured)

    note = server.NoteInput(
        fields={"Front": "Question"},
        images=[{"image_base64": IMAGE_B64, "target_field": "extra"}],
    )

    result = await server.add_from_model.fn("Deck", "Basic", [note])

    assert result.added == 1
    warns = [detail for detail in result.details if detail.get("warn") == "unknown_target_field"]
    assert warns and warns[0]["index"] == 0
    assert warns[0]["field"] == "extra"

    add_notes_payload = captured.get("addNotes")
    assert isinstance(add_notes_payload, dict)
    assert add_notes_payload["notes"][0]["fields"].get("Back", "") == ""


@pytest.mark.anyio
async def test_add_notes_image_target_field_normalized(monkeypatch):
    captured: dict[str, object] = {}
    _setup_common_monkeypatches(monkeypatch, captured)

    note = server.NoteInput(
        fields={"Front": "Question", "Back": ""},
        images=[{"image_base64": IMAGE_B64, "target_field": "back"}],
    )
    args = server.AddNotesArgs(deck="Deck", model="Basic", notes=[note])

    result = await server.add_notes.fn(args)

    assert result.added == 1
    assert not any(detail.get("warn") == "unknown_target_field" for detail in result.details)

    add_notes_payload = captured.get("addNotes")
    assert isinstance(add_notes_payload, dict)
    fields = add_notes_payload["notes"][0]["fields"]
    assert "<img src=\"img-alias.jpg\"" in fields.get("Back", "")


@pytest.mark.anyio
async def test_add_notes_unknown_target_field_warn(monkeypatch):
    captured: dict[str, object] = {}
    _setup_common_monkeypatches(monkeypatch, captured)

    note = server.NoteInput(
        fields={"Front": "Question", "Back": ""},
        images=[{"image_base64": IMAGE_B64, "target_field": "oops"}],
    )
    args = server.AddNotesArgs(deck="Deck", model="Basic", notes=[note])

    result = await server.add_notes.fn(args)

    assert result.added == 1
    warns = [detail for detail in result.details if detail.get("warn") == "unknown_target_field"]
    assert warns and warns[0]["index"] == 0
    assert warns[0]["field"] == "oops"

    add_notes_payload = captured.get("addNotes")
    assert isinstance(add_notes_payload, dict)
    assert add_notes_payload["notes"][0]["fields"].get("Back", "") == ""
