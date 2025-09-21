import base64
import re
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
    import fastmcp as _fastmcp_mod  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - executed in minimal test environments
    def _noop_decorator(*args, **kwargs):
        def decorator(func):
            return func

        return decorator

    fastmcp_stub = types.SimpleNamespace(
        FastMCP=lambda *args, **kwargs: types.SimpleNamespace(
            tool=_noop_decorator,
            custom_route=_noop_decorator,
            name=kwargs.get("name", args[0] if args else "anki-mcp"),
        )
    )
    sys.modules.setdefault("fastmcp", fastmcp_stub)

try:  # pragma: no cover - exercised only when dependency missing
    import pydantic as _pydantic_mod  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - executed in minimal test environments
    pydantic_stub = types.SimpleNamespace(
        BaseModel=object,
        Field=_field_stub,
        constr=lambda **kwargs: str,
        AnyHttpUrl=str,
    )
    sys.modules.setdefault("pydantic", pydantic_stub)

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import server


@pytest.fixture
def anyio_backend():
    return "asyncio"


class DummyUUID:
    def __init__(self, hex_value: str):
        self.hex = hex_value


@pytest.mark.anyio
async def test_add_from_model_sanitizes_data_url(monkeypatch):
    raw_bytes = b"png-payload"
    original_b64 = base64.b64encode(raw_bytes).decode("ascii")
    data_url = f"  data:image/png;base64,{original_b64}  "

    stored: dict[str, str] = {}

    async def fake_store_media_file(filename: str, data_b64: str):
        stored["filename"] = filename
        stored["data"] = data_b64

    async def fake_anki_call(action: str, params: dict):
        if action == "createDeck":
            return True
        if action == "modelFieldNames":
            return ["Front", "Back"]
        if action == "modelTemplates":
            return {"Card 1": {"Front": "{{Front}}", "Back": "{{Back}}"}}
        if action == "modelStyling":
            return {"css": ""}
        if action == "addNotes":
            return [123]
        raise AssertionError(f"unexpected action: {action}")

    monkeypatch.setattr("anki_mcp.services.client.store_media_file", fake_store_media_file)
    monkeypatch.setattr("anki_mcp.services.client.anki_call", fake_anki_call)
    monkeypatch.setattr(server.uuid, "uuid4", lambda: DummyUUID("abc123"))

    image = server.ImageSpec(image_base64=data_url, target_field="Back")
    note = server.NoteInput(fields={"Front": "Question"}, images=[image])

    result = await server.add_from_model.fn("Default", "Basic", [note])

    assert stored["data"] == base64.b64encode(raw_bytes).decode("ascii")
    assert stored["filename"] == "abc123.png"
    assert result.added == 1
    assert all("note is empty" not in str(detail) for detail in result.details)


@pytest.mark.anyio
async def test_process_data_urls_accepts_mixed_case_prefix(monkeypatch):
    raw_bytes = b"case-png"
    original_b64 = base64.b64encode(raw_bytes).decode("ascii")
    data_url = f"DATA:image/PNG;BASE64,{original_b64}"

    stored: dict[str, str] = {}

    async def fake_store_media_file(filename: str, data_b64: str):
        stored["filename"] = filename
        stored["data"] = data_b64

    monkeypatch.setattr("anki_mcp.services.client.store_media_file", fake_store_media_file)

    original_value = f"Before text {data_url}"
    fields = {"Back": original_value}
    results: list[dict[str, object]] = []

    await server.process_data_urls_in_fields(fields, results, note_index=0)

    assert stored["data"] == base64.b64encode(raw_bytes).decode("ascii")
    assert stored["filename"].endswith(".png")
    expected = server.ensure_img_tag(
        original_value.replace(data_url, "").strip(), stored["filename"]
    )
    assert fields["Back"] == expected
    assert all("warn" not in detail for detail in results)


@pytest.mark.anyio
async def test_data_url_and_images_share_same_html(monkeypatch):
    raw_bytes = b"unified"
    original_b64 = base64.b64encode(raw_bytes).decode("ascii")
    data_url = f"data:image/png;base64,{original_b64}"

    stored_calls: list[tuple[str, str]] = []

    async def fake_store_media_file(filename: str, data_b64: str):
        stored_calls.append((filename, data_b64))

    captured: dict[str, object] = {}

    async def fake_anki_call(action: str, params: dict):
        if action == "createDeck":
            return True
        if action == "modelFieldNames":
            return ["Front", "Back"]
        if action == "modelTemplates":
            return {"Card 1": {"Front": "{{Front}}", "Back": "{{Back}}"}}
        if action == "modelStyling":
            return {"css": ""}
        if action == "addNotes":
            captured["fields_html"] = params["notes"][0]["fields"]["Back"]
            return [456]
        raise AssertionError(f"unexpected action: {action}")

    monkeypatch.setattr("anki_mcp.services.client.store_media_file", fake_store_media_file)
    monkeypatch.setattr("anki_mcp.services.client.anki_call", fake_anki_call)
    monkeypatch.setattr(server.uuid, "uuid4", lambda: DummyUUID("imguuid"))

    fields = {"Back": f"Existing {data_url}"}
    results: list[dict[str, object]] = []
    await server.process_data_urls_in_fields(fields, results, note_index=0)

    assert not [detail for detail in results if "warn" in detail]
    data_url_html = fields["Back"]
    assert stored_calls, "data URL should trigger media storage"
    image = server.ImageSpec(image_base64=data_url, target_field="Back")
    note = server.NoteInput(fields={"Front": "Q", "Back": "Existing"}, images=[image])
    await server.add_from_model.fn("Default", "Basic", [note])

    assert "fields_html" in captured
    images_html = captured["fields_html"]
    assert len(stored_calls) >= 2, "image helper should store media twice"

    normalized_data_html = re.sub(r'src="[^"]+"', 'src="FILE"', data_url_html)
    normalized_images_html = re.sub(r'src="[^"]+"', 'src="FILE"', images_html)
    assert normalized_data_html == normalized_images_html


@pytest.mark.anyio
async def test_add_from_model_target_field_is_case_insensitive(monkeypatch):
    stored: dict[str, str] = {}
    captured: dict[str, object] = {}

    async def fake_store_media_file(filename: str, data_b64: str):
        stored["filename"] = filename
        stored["data"] = data_b64

    async def fake_anki_call(action: str, params: dict):
        if action == "createDeck":
            return True
        if action == "modelFieldNames":
            return ["Front", "Back"]
        if action == "modelTemplates":
            return {"Card 1": {"Front": "{{Front}}", "Back": "{{Back}}"}}
        if action == "modelStyling":
            return {"css": ""}
        if action == "addNotes":
            captured["payload"] = params
            return [555]
        raise AssertionError(f"unexpected action: {action}")

    monkeypatch.setattr("anki_mcp.services.client.store_media_file", fake_store_media_file)
    monkeypatch.setattr("anki_mcp.services.client.anki_call", fake_anki_call)
    monkeypatch.setattr(server.uuid, "uuid4", lambda: DummyUUID("case-img"))

    image = server.ImageSpec(image_base64="data:image/png;base64,Zm9v", target_field="back")
    note = server.NoteInput(fields={"Front": "Question"}, images=[image])

    result = await server.add_from_model.fn("Default", "Basic", [note])

    assert result.added == 1
    payload = captured.get("payload")
    assert isinstance(payload, dict)
    note_fields = payload["notes"][0]["fields"]
    assert "<img src=\"case-img.png\"" in note_fields.get("Back", "")


@pytest.mark.anyio
async def test_add_from_model_unknown_target_field_warn(monkeypatch):
    captured: dict[str, object] = {}

    async def fake_anki_call(action: str, params: dict):
        if action == "createDeck":
            return True
        if action == "modelFieldNames":
            return ["Front", "Back"]
        if action == "modelTemplates":
            return {"Card 1": {"Front": "{{Front}}", "Back": "{{Back}}"}}
        if action == "modelStyling":
            return {"css": ""}
        if action == "addNotes":
            captured["addNotes"] = params
            return [4321]
        raise AssertionError(f"unexpected action: {action}")

    monkeypatch.setattr("anki_mcp.services.client.anki_call", fake_anki_call)

    image = server.ImageSpec(image_base64="data:image/png;base64,Zm9v", target_field="Summary")
    note = server.NoteInput(fields={"Front": "Question"}, images=[image])

    result = await server.add_from_model.fn("Default", "Basic", [note])

    assert result.added == 1
    warns = [detail for detail in result.details if detail.get("warn") == "unknown_target_field"]
    assert warns and warns[0]["index"] == 0
    assert warns[0]["field"] == "Summary"

    add_notes_payload = captured.get("addNotes")
    assert isinstance(add_notes_payload, dict)
    note_fields = add_notes_payload["notes"][0]["fields"]
    assert note_fields.get("Back", "") == ""


@pytest.mark.anyio
async def test_note_input_accepts_url_alias(monkeypatch):
    stored_calls: list[dict[str, str]] = []
    captured: dict[str, object] = {}

    async def fake_fetch_image(url: str, max_side: int) -> str:
        captured["fetched"] = {"url": url, "max_side": max_side}
        return base64.b64encode(b"alias-image").decode("ascii")

    async def fake_store_media_file(filename: str, data_b64: str):
        stored_calls.append({"filename": filename, "data": data_b64})

    async def fake_anki_call(action: str, params: dict):
        if action == "createDeck":
            captured["createDeck"] = params
            return True
        if action == "modelFieldNames":
            return ["Front", "Back"]
        if action == "modelTemplates":
            raise AssertionError("modelTemplates should not be called for add_notes")
        if action == "modelStyling":
            raise AssertionError("modelStyling should not be called for add_notes")
        if action == "addNotes":
            captured["addNotes"] = params
            return [987]
        raise AssertionError(f"unexpected action: {action}")

    monkeypatch.setattr("anki_mcp.services.media.fetch_image_as_base64", fake_fetch_image)
    monkeypatch.setattr("anki_mcp.services.client.store_media_file", fake_store_media_file)
    monkeypatch.setattr("anki_mcp.services.client.anki_call", fake_anki_call)
    monkeypatch.setattr(server.uuid, "uuid4", lambda: DummyUUID("img-alias"))

    note = server.NoteInput(
        fields={"Front": "Alias"},
        images=[{"url": "https://example.com/img.jpg"}],
    )

    image = note.images[0]
    assert str(image.image_url) == "https://example.com/img.jpg"

    args = server.AddNotesArgs(deck="Deck", model="Basic", notes=[note])
    result = await server.add_notes.fn(args)

    assert result.added == 1
    assert all("warn" not in detail for detail in result.details)
    assert stored_calls and stored_calls[0]["data"].startswith("YWxpYXMt")
    assert captured.get("fetched") == {"url": "https://example.com/img.jpg", "max_side": image.max_side}

    add_notes_payload = captured.get("addNotes")
    assert isinstance(add_notes_payload, dict)
    fields = add_notes_payload["notes"][0]["fields"]
    assert "<img src=\"img-alias.jpg\"" in fields.get("Back", "")

