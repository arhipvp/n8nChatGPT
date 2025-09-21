"""Прикладные сервисы для взаимодействия с Anki и обработкой заметок."""

from __future__ import annotations

import base64
import hashlib
import re
import uuid
from io import BytesIO
from typing import Any, Dict, List, Optional, Tuple

import httpx
from PIL import Image

from ..compat import model_validate
from ..config import ANKI_URL
from ..schemas import NoteInfo


async def anki_call(action: str, params: dict):
    payload = {"action": action, "version": 6, "params": params}
    async with httpx.AsyncClient(timeout=25) as client:
        response = await client.post(ANKI_URL, json=payload)
        response.raise_for_status()
        data = response.json()
        if data.get("error"):
            raise RuntimeError(f"Anki error: {data['error']}")
        return data["result"]


async def store_media_file(filename: str, data_b64: str):
    return await anki_call("storeMediaFile", {"filename": filename, "data": data_b64})


async def fetch_image_as_base64(url: str, max_side: int) -> str:
    if max_side < 1:
        raise ValueError("max_side must be at least 1")

    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        response = await client.get(url)
        response.raise_for_status()
        content = response.content

    try:
        original = Image.open(BytesIO(content))
        target_format = "JPEG"

        if "A" in (original.getbands() or ()):  # RGBA/LA/etc.
            rgba = original.convert("RGBA")
            background = Image.new("RGB", rgba.size, (255, 255, 255))
            alpha = rgba.getchannel("A")
            background.paste(rgba, mask=alpha)
            image = background
        elif original.mode == "P" and "transparency" in original.info:
            rgba = original.convert("RGBA")
            background = Image.new("RGB", rgba.size, (255, 255, 255))
            alpha = rgba.getchannel("A")
            background.paste(rgba, mask=alpha)
            image = background
        elif original.mode != "RGB":
            image = original.convert("RGB")
        else:
            image = original

        width, height = image.size
        scale = max(width, height) / max_side if max(width, height) > max_side else 1.0
        if scale > 1.0:
            new_width = max(1, round(width / scale))
            new_height = max(1, round(height / scale))
            image = image.resize((new_width, new_height))
        buffer = BytesIO()
        image.save(buffer, format=target_format, quality=85)
        content = buffer.getvalue()
    except Exception:
        pass

    return base64.b64encode(content).decode("ascii")


IMG_TAG_TEMPLATE = '<div><img src="{src}" style="max-width:100%;height:auto"/></div>'


def build_img_tag(filename: str) -> str:
    return IMG_TAG_TEMPLATE.format(src=filename)


def ensure_img_tag(existing: str, filename: str) -> str:
    existing = existing or ""
    tag = build_img_tag(filename)
    if re.search(rf'src=["\']{re.escape(filename)}["\']', existing, re.IGNORECASE):
        return existing

    trimmed = existing.rstrip()
    if not trimmed:
        return tag
    return f"{trimmed}\n\n{tag}"


DATA_URL_RE = re.compile(r"^data:image/([a-zA-Z0-9+.\-]+);base64,(.+)$", re.IGNORECASE)
DATA_URL_INLINE_RE = re.compile(
    r"data:image/([a-zA-Z0-9+.\-]+);base64,([a-zA-Z0-9+/=]+)", re.IGNORECASE
)


def ext_from_mime(mime_subtype: str) -> str:
    subtype = mime_subtype.lower()
    if subtype in ("jpeg", "jpg", "pjpeg"):
        return "jpg"
    if subtype in ("png", "x-png"):
        return "png"
    if subtype in ("webp",):
        return "webp"
    if subtype in ("gif",):
        return "gif"
    return "png"


def sanitize_image_payload(payload: str) -> Tuple[str, Optional[str]]:
    trimmed = (payload or "").strip()
    if not trimmed:
        raise ValueError("image payload is empty")

    match = DATA_URL_RE.match(trimmed)
    if match:
        mime_subtype, b64_payload = match.group(1), match.group(2).strip()
        try:
            raw = base64.b64decode(b64_payload, validate=True)
        except Exception as exc:  # pragma: no cover - error path
            raise ValueError(f"invalid base64 image data: {exc}") from exc
        clean_b64 = base64.b64encode(raw).decode("ascii")
        return clean_b64, ext_from_mime(mime_subtype)

    try:
        raw = base64.b64decode(trimmed, validate=True)
    except Exception as exc:  # pragma: no cover - error path
        raise ValueError(f"invalid base64 image data: {exc}") from exc
    clean_b64 = base64.b64encode(raw).decode("ascii")
    return clean_b64, None


async def process_data_urls_in_fields(
    fields: Dict[str, str], results: List[dict], note_index: int
):
    for key, value in list(fields.items()):
        if not isinstance(value, str):
            continue

        matches = list(DATA_URL_INLINE_RE.finditer(value))
        if not matches:
            trimmed = value.strip()
            match = DATA_URL_RE.match(trimmed)
            matches = [match] if match else []
            if matches:
                value = trimmed
        if not matches:
            continue

        saved_files: List[str] = []
        rebuilt: List[str] = []
        cursor = 0

        for match in matches:
            data_url = match.group(0)
            try:
                clean_b64, ext_hint = sanitize_image_payload(data_url)
                raw = base64.b64decode(clean_b64, validate=True)
                digest = hashlib.sha1(raw).hexdigest()
                mime_subtype = match.group(1) if match.lastindex else None
                extension = ext_hint or (
                    ext_from_mime(mime_subtype) if mime_subtype else "png"
                )
                filename = f"img_{digest}.{extension}"
                await store_media_file(filename, clean_b64)
                saved_files.append(filename)
                results.append({"index": note_index, "info": f"data_url_saved:{key}->{filename}"})
            except Exception as exc:
                results.append({"index": note_index, "warn": f"data_url_failed:{key}: {exc}"})
                rebuilt.append(value[cursor : match.end()])
                cursor = match.end()
                continue

            rebuilt.append(value[cursor : match.start()])
            cursor = match.end()

        rebuilt.append(value[cursor:])
        new_value = "".join(rebuilt)
        clean_text = new_value.strip()
        for filename in saved_files:
            clean_text = ensure_img_tag(clean_text, filename)

        fields[key] = clean_text


async def get_model_fields_templates(
    model: str,
) -> Tuple[List[str], Dict[str, Dict[str, str]], str]:
    fields = await anki_call("modelFieldNames", {"modelName": model})
    templates = await anki_call("modelTemplates", {"modelName": model})
    styling = await anki_call("modelStyling", {"modelName": model})
    return fields, templates, styling.get("css", "")


async def get_model_field_names(model: str) -> List[str]:
    return await anki_call("modelFieldNames", {"modelName": model})


def normalize_fields_for_model(
    user_fields: Dict[str, str], model_fields: List[str]
) -> Tuple[Dict[str, str], int, List[str]]:
    normalized: Dict[str, str] = {}
    lower_map = {key.lower(): key for key in user_fields.keys()}
    matched_keys: List[str] = []
    for model_field in model_fields:
        key = lower_map.get(model_field.lower())
        if key:
            normalized[model_field] = user_fields.get(key, "")
            matched_keys.append(key)
        else:
            normalized[model_field] = ""

    unknown_fields = [key for key in user_fields.keys() if key not in matched_keys]
    return normalized, len(matched_keys), sorted(unknown_fields)


def normalize_and_validate_note_fields(
    user_fields: Dict[str, str], model_fields: List[str]
) -> Dict[str, str]:
    fields, matched_count, unknown_fields = normalize_fields_for_model(
        user_fields, model_fields
    )

    if not model_fields:
        raise ValueError("Model has no fields configured")

    if matched_count == 0 or not fields.get(model_fields[0]):
        expected = ", ".join(repr(name) for name in model_fields)
        provided = ", ".join(repr(name) for name in unknown_fields)
        raise ValueError(
            "Unknown note fields: "
            f"[{provided}]"
            f". Expected fields: [{expected}]. "
            f"Ensure required field '{model_fields[0]}' is provided."
        )

    return fields


def _normalize_note_fields_payload(raw_fields: Any) -> Dict[str, str]:
    if not isinstance(raw_fields, dict):
        return {}

    normalized: Dict[str, str] = {}
    for key, value in raw_fields.items():
        if isinstance(value, dict) and "value" in value:
            candidate = value.get("value")
        else:
            candidate = value

        if candidate is None:
            normalized_value = ""
        elif isinstance(candidate, str):
            normalized_value = candidate
        else:
            normalized_value = str(candidate)

        normalized[str(key)] = normalized_value

    return normalized


def _normalize_note_tags(raw_tags: Any) -> List[str]:
    if not isinstance(raw_tags, list):
        return []

    tags: List[str] = []
    for tag in raw_tags:
        if tag is None:
            continue
        if isinstance(tag, str):
            trimmed = tag.strip()
            if trimmed:
                tags.append(trimmed)
        else:
            tags.append(str(tag))
    return tags


def _normalize_note_cards(raw_cards: Any) -> List[int]:
    if not isinstance(raw_cards, list):
        return []

    cards: List[int] = []
    for card in raw_cards:
        if card is None:
            continue
        if isinstance(card, int):
            cards.append(card)
            continue
        if isinstance(card, float):
            cards.append(int(card))
            continue
        if isinstance(card, str):
            stripped = card.strip()
            if not stripped:
                continue
            try:
                cards.append(int(stripped))
            except ValueError:
                continue
    return cards


def _normalize_note_entry(raw_note: Any, index: int) -> Optional[NoteInfo]:
    if raw_note is None:
        return None
    if not isinstance(raw_note, dict):
        raise ValueError(f"notesInfo[{index}] must be an object or null")

    note_id_raw = raw_note.get("noteId")
    if isinstance(note_id_raw, int):
        note_id = note_id_raw
    elif isinstance(note_id_raw, str):
        stripped = note_id_raw.strip()
        if not stripped:
            raise ValueError(f"notesInfo[{index}].noteId is empty")
        try:
            note_id = int(stripped)
        except ValueError as exc:
            raise ValueError(
                f"notesInfo[{index}].noteId must be an integer, got {note_id_raw!r}"
            ) from exc
    else:
        raise ValueError(
            f"notesInfo[{index}].noteId must be an integer, got {note_id_raw!r}"
        )

    payload = {
        "noteId": note_id,
        "modelName": raw_note.get("modelName"),
        "deckName": raw_note.get("deckName"),
        "tags": _normalize_note_tags(raw_note.get("tags")),
        "fields": _normalize_note_fields_payload(raw_note.get("fields")),
        "cards": _normalize_note_cards(raw_note.get("cards")),
    }

    return model_validate(NoteInfo, payload)


def normalize_notes_info(raw_notes: Any) -> List[Optional[NoteInfo]]:
    if not isinstance(raw_notes, list):
        raise ValueError("notesInfo response must be a list")

    normalized: List[Optional[NoteInfo]] = []
    for index, raw_note in enumerate(raw_notes):
        normalized.append(_normalize_note_entry(raw_note, index))
    return normalized


__all__ = [
    "ANKI_URL",
    "DATA_URL_INLINE_RE",
    "DATA_URL_RE",
    "IMG_TAG_TEMPLATE",
    "anki_call",
    "build_img_tag",
    "ensure_img_tag",
    "ext_from_mime",
    "fetch_image_as_base64",
    "get_model_field_names",
    "get_model_fields_templates",
    "httpx",
    "normalize_and_validate_note_fields",
    "normalize_fields_for_model",
    "normalize_notes_info",
    "process_data_urls_in_fields",
    "sanitize_image_payload",
    "store_media_file",
]
