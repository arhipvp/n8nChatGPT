import base64
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

    monkeypatch.setattr(server, "store_media_file", fake_store_media_file)
    monkeypatch.setattr(server, "anki_call", fake_anki_call)
    monkeypatch.setattr(server.uuid, "uuid4", lambda: DummyUUID("abc123"))

    image = server.ImageSpec(image_base64=data_url, target_field="Back")
    note = server.NoteInput(fields={"Front": "Question"}, images=[image])

    result = await server.add_from_model.fn("Default", "Basic", [note])

    assert stored["data"] == base64.b64encode(raw_bytes).decode("ascii")
    assert stored["filename"] == "abc123.png"
    assert result.added == 1
    assert all("note is empty" not in str(detail) for detail in result.details)


@pytest.mark.anyio
async def test_add_from_model_target_field_case_insensitive(monkeypatch):
    stored: dict[str, str] = {}
    captured_fields: dict[str, str] = {}

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
            captured_fields.update(params["notes"][0]["fields"])
            return [999]
        raise AssertionError(f"unexpected action: {action}")

    monkeypatch.setattr(server, "store_media_file", fake_store_media_file)
    monkeypatch.setattr(server, "anki_call", fake_anki_call)
    monkeypatch.setattr(server.uuid, "uuid4", lambda: DummyUUID("abc123"))

    img_payload = base64.b64encode(b"gif-bytes").decode("ascii")
    image = server.ImageSpec(image_base64=img_payload, target_field="back")
    note = server.NoteInput(fields={"Front": "Question"}, images=[image])

    result = await server.add_from_model.fn("Default", "Basic", [note])

    assert captured_fields.get("Back")
    assert "back" not in captured_fields
    assert stored["filename"].endswith(".jpg")  # gif -> jpg after sanitize
    assert result.added == 1
    assert all("unknown_target_field" not in detail.get("warn", "") for detail in result.details)


@pytest.mark.anyio
async def test_add_from_model_target_field_invalid(monkeypatch):
    stored: list[str] = []

    async def fake_store_media_file(filename: str, data_b64: str):
        stored.append(filename)

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
            return [321]
        raise AssertionError(f"unexpected action: {action}")

    monkeypatch.setattr(server, "store_media_file", fake_store_media_file)
    monkeypatch.setattr(server, "anki_call", fake_anki_call)
    monkeypatch.setattr(server.uuid, "uuid4", lambda: DummyUUID("deadbeef"))

    img_payload = base64.b64encode(b"png-bytes").decode("ascii")
    image = server.ImageSpec(image_base64=img_payload, target_field="NotAField")
    note = server.NoteInput(fields={"Front": "Question"}, images=[image])

    result = await server.add_from_model.fn("Default", "Basic", [note])

    assert not stored
    warn_messages = [detail["warn"] for detail in result.details if "warn" in detail]
    assert any("unknown_target_field" in msg for msg in warn_messages)
    assert any("['Front', 'Back']" in msg for msg in warn_messages)

