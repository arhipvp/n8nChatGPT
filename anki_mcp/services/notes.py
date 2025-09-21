"""Нормализация данных заметок Anki."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from ..compat import model_validate
from ..schemas import NoteInfo


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
    "normalize_and_validate_note_fields",
    "normalize_fields_for_model",
    "normalize_notes_info",
]
