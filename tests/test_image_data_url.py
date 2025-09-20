import base64
import sys
import types
from pathlib import Path

import pytest


def _field_stub(*args, **kwargs):
    if "default" in kwargs:
        return kwargs["default"]
    if "default_factory" in kwargs:
        return kwargs["default_factory"]()
    return None


try:  # pragma: no cover - executed only when dependency is unavailable
    import fastmcp as _fastmcp_mod  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - fallback for minimal environments
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


try:  # pragma: no cover - executed only when dependency is unavailable
    import pydantic as _pydantic_mod  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - fallback for minimal environments
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


def _make_data_url(payload: bytes) -> tuple[str, str]:
    encoded = base64.b64encode(payload).decode("ascii")
    data_url = f"  data:image/png;base64,{encoded}  "
    return data_url, encoded


@pytest.mark.asyncio
async def test_add_from_model_sanitizes_data_url_images(monkeypatch):
    raw_bytes = b"png-bytes"
    data_url, expected_b64 = _make_data_url(raw_bytes)

    stored_payloads: list[tuple[str, str]] = []

    async def fake_store_media_file(filename: str, data_b64: str):
        stored_payloads.append((filename, data_b64))
        return None

    monkeypatch.setattr(server, "store_media_file", fake_store_media_file)

    fake_uuid = types.SimpleNamespace(hex="fixeduuid")
    monkeypatch.setattr(server.uuid, "uuid4", lambda: fake_uuid)

    recorded_notes: list[dict] | None = None

    async def fake_anki_call(action: str, params: dict):
        nonlocal recorded_notes
        if action == "createDeck":
            return None
        if action == "modelFieldNames":
            return ["Front", "Back"]
        if action == "modelTemplates":
            return {}
        if action == "modelStyling":
            return {"css": ""}
        if action == "addNotes":
            recorded_notes = params["notes"]
            return [123]
        raise AssertionError(f"Unexpected action: {action}")

    monkeypatch.setattr("server.anki_call", fake_anki_call)

    note = server.NoteInput(
        fields={"Front": "Question"},
        images=[server.ImageSpec(image_base64=data_url, target_field="Back")],
    )

    result = await server.add_from_model(deck="Deck", model="Basic", items=[note])

    assert stored_payloads == [("fixeduuid.png", expected_b64)]
    assert recorded_notes is not None
    assert "fixeduuid.png" in recorded_notes[0]["fields"]["Back"]
    assert not any("warn" in detail for detail in result.details)
    assert result.details[0]["status"] == "ok"


@pytest.mark.asyncio
async def test_add_notes_sanitizes_data_url_images(monkeypatch):
    raw_bytes = b"another-png"
    data_url, expected_b64 = _make_data_url(raw_bytes)

    stored_payloads: list[tuple[str, str]] = []

    async def fake_store_media_file(filename: str, data_b64: str):
        stored_payloads.append((filename, data_b64))
        return None

    monkeypatch.setattr(server, "store_media_file", fake_store_media_file)

    fake_uuid = types.SimpleNamespace(hex="uuidtwo")
    monkeypatch.setattr(server.uuid, "uuid4", lambda: fake_uuid)

    recorded_notes: list[dict] | None = None

    async def fake_anki_call(action: str, params: dict):
        nonlocal recorded_notes
        if action == "createDeck":
            return None
        if action == "addNotes":
            recorded_notes = params["notes"]
            return [456]
        raise AssertionError(f"Unexpected action: {action}")

    monkeypatch.setattr("server.anki_call", fake_anki_call)

    args = server.AddNotesArgs(
        deck="Deck",
        model="Basic",
        notes=[
            server.NoteInput(
                fields={"Front": "Front content"},
                images=[server.ImageSpec(image_base64=data_url, target_field="Back")],
            )
        ],
    )

    result = await server.add_notes(args)

    assert stored_payloads == [("uuidtwo.png", expected_b64)]
    assert recorded_notes is not None
    assert "uuidtwo.png" in recorded_notes[0]["fields"]["Back"]
    assert not any("warn" in detail for detail in result.details)
    assert result.details[0]["status"] == "ok"
