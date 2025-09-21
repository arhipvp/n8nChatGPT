"""Инструменты MCP, связанные с Anki."""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional, Tuple, Union

from .. import app
from ..compat import model_validate
from ..config import DEFAULT_DECK, DEFAULT_MODEL
from ..schemas import (
    AddNotesArgs,
    AddNotesResult,
    FindNotesArgs,
    FindNotesResponse,
    ModelInfo,
    NOTE_RESERVED_TOP_LEVEL_KEYS,
    NoteInfo,
    NoteInfoArgs,
    NoteInfoResponse,
    NoteInput,
)
from ..services import anki as anki_services


@app.tool(name="anki.find_notes")
async def find_notes(args: FindNotesArgs) -> FindNotesResponse:
    raw_note_ids = await anki_services.anki_call("findNotes", {"query": args.query})
    if not isinstance(raw_note_ids, list):
        raise ValueError("findNotes response must be a list of note ids")

    normalized_ids: List[int] = []
    for index, raw_id in enumerate(raw_note_ids):
        if isinstance(raw_id, bool):
            raise ValueError(
                f"findNotes returned non-integer value at index {index}: {raw_id!r}"
            )
        try:
            note_id = int(raw_id)
        except (TypeError, ValueError):
            raise ValueError(
                f"findNotes returned non-integer value at index {index}: {raw_id!r}"
            ) from None
        normalized_ids.append(note_id)

    offset = args.offset or 0
    if offset:
        normalized_ids = normalized_ids[offset:]
    if args.limit is not None:
        normalized_ids = normalized_ids[: args.limit]

    notes: List[Optional[NoteInfo]] = []
    if normalized_ids:
        raw_notes = await anki_services.anki_call("notesInfo", {"notes": normalized_ids})
        notes = anki_services.normalize_notes_info(raw_notes)

    return FindNotesResponse(note_ids=normalized_ids, notes=notes)


@app.tool(name="anki.note_info")
async def note_info(args: NoteInfoArgs) -> NoteInfoResponse:
    raw_notes = await anki_services.anki_call("notesInfo", {"notes": args.note_ids})
    normalized = anki_services.normalize_notes_info(raw_notes)
    return NoteInfoResponse(notes=normalized)


@app.tool(name="anki.model_info")
async def model_info(model: str = DEFAULT_MODEL) -> ModelInfo:
    fields, templates, css = await anki_services.get_model_fields_templates(model)
    return ModelInfo(model=model, fields=fields, templates=templates, styling=css)


@app.tool(name="anki.add_from_model")
async def add_from_model(
    deck: str = DEFAULT_DECK,
    model: str = DEFAULT_MODEL,
    items: Optional[List[Union[NoteInput, Dict[str, str]]]] = None,
) -> AddNotesResult:
    if items is None:
        raise ValueError("items must be provided")

    await anki_services.anki_call("createDeck", {"deck": deck})

    normalized_items: List[NoteInput] = []
    for index, raw_item in enumerate(items):
        if isinstance(raw_item, NoteInput):
            note = raw_item
        elif isinstance(raw_item, dict):
            payload: Dict[str, Any]
            if "fields" in raw_item:
                payload = raw_item  # type: ignore[assignment]
            else:
                candidate_fields = {
                    key: raw_item[key]
                    for key in raw_item.keys()
                    if key not in NOTE_RESERVED_TOP_LEVEL_KEYS
                }
                if not candidate_fields:
                    raise ValueError(
                        "Каждая заметка должна содержать хотя бы одно поле, например {'Front': 'Question'}."
                    )

                payload = {"fields": candidate_fields}
                for key in NOTE_RESERVED_TOP_LEVEL_KEYS:
                    if key in raw_item:
                        payload[key] = raw_item[key]

            try:
                note = model_validate(NoteInput, payload)
            except Exception as exc:  # pragma: no cover - защитный хэндлинг
                raise ValueError(f"Invalid note at index {index}: {exc}") from exc
        else:
            raise TypeError(
                f"items[{index}] must be NoteInput or dict, got {type(raw_item).__name__}"
            )

        normalized_items.append(note)

    decks_to_create = {deck}
    model_fields_cache: Dict[str, List[str]] = {}
    field_aliases_cache: Dict[str, Dict[str, str]] = {}

    async def _ensure_model_context(model_name: str) -> Tuple[List[str], Dict[str, str]]:
        cached_fields = model_fields_cache.get(model_name)
        if cached_fields is None:
            fields = await anki_services.get_model_field_names(model_name)
            model_fields_cache[model_name] = fields
            field_aliases_cache[model_name] = {field.lower(): field for field in fields}
        return model_fields_cache[model_name], field_aliases_cache[model_name]

    for note in normalized_items:
        if note.deck:
            decks_to_create.add(note.deck)

    for deck_name in decks_to_create:
        await anki_services.anki_call("createDeck", {"deck": deck_name})

    notes_payload: List[dict] = []
    results: List[dict] = []
    added = skipped = 0

    for index, note in enumerate(normalized_items):
        note_deck = note.deck or deck
        note_model = note.model or model

        model_fields, field_aliases = await _ensure_model_context(note_model)

        fields = anki_services.normalize_and_validate_note_fields(note.fields, model_fields)

        await anki_services.process_data_urls_in_fields(fields, results, index)

        for img in note.images:
            ext_hint: Optional[str] = None
            if img.image_base64:
                try:
                    data_b64, ext_hint = anki_services.sanitize_image_payload(img.image_base64)
                except ValueError as exc:
                    results.append({"index": index, "warn": f"invalid_image_base64: {exc}"})
                    continue
            elif img.image_url:
                try:
                    data_b64 = await anki_services.fetch_image_as_base64(str(img.image_url), img.max_side)
                except Exception as exc:
                    results.append({"index": index, "warn": f"fetch_image_failed: {exc}"})
                    continue
            else:
                results.append({"index": index, "warn": "no_image_provided"})
                continue

            filename = img.filename or f"{uuid.uuid4().hex}.{ext_hint or 'jpg'}"
            canonical_target = field_aliases.get(img.target_field.lower())
            if not canonical_target:
                results.append(
                    {
                        "index": index,
                        "warn": "unknown_target_field",
                        "field": img.target_field,
                    }
                )
                continue
            try:
                await anki_services.store_media_file(filename, data_b64)
                previous = fields[canonical_target]
                fields[canonical_target] = anki_services.ensure_img_tag(previous, filename)
            except Exception as exc:
                results.append({"index": index, "warn": f"store_media_failed: {exc}"})

        notes_payload.append(
            {
                "deckName": note_deck,
                "modelName": note_model,
                "fields": fields,
                "tags": note.tags,
                "options": {"allowDuplicate": False},
            }
        )

    try:
        response = await anki_services.anki_call("addNotes", {"notes": notes_payload})
        for idx, note_id in enumerate(response):
            dedup_key = normalized_items[idx].dedup_key
            if note_id is None:
                skipped += 1
                detail = {"index": idx, "status": "duplicate"}
                if dedup_key is not None:
                    detail["dedup_key"] = dedup_key
                results.append(detail)
            else:
                added += 1
                detail = {"index": idx, "status": "ok", "noteId": note_id}
                if dedup_key is not None:
                    detail["dedup_key"] = dedup_key
                results.append(detail)
    except Exception as exc:
        raise RuntimeError(f"addNotes_failed: {exc}") from exc

    return AddNotesResult(added=added, skipped=skipped, details=results)


@app.tool(name="anki.add_notes")
async def add_notes(args: AddNotesArgs) -> AddNotesResult:
    notes_payload: List[dict] = []
    results: List[dict] = []
    added = skipped = 0
    normalized_notes: List[NoteInput] = list(args.notes)

    decks_to_create = {args.deck}
    model_fields_cache: Dict[str, List[str]] = {}
    canonical_field_map_cache: Dict[str, Dict[str, str]] = {}

    async def _ensure_model_context(model_name: str) -> Tuple[List[str], Dict[str, str]]:
        cached_fields = model_fields_cache.get(model_name)
        if cached_fields is None:
            fields = await anki_services.get_model_field_names(model_name)
            model_fields_cache[model_name] = fields
            canonical_field_map_cache[model_name] = {
                field.lower(): field for field in fields
            }
        return model_fields_cache[model_name], canonical_field_map_cache[model_name]

    for note in normalized_notes:
        if note.deck:
            decks_to_create.add(note.deck)

    for deck_name in decks_to_create:
        await anki_services.anki_call("createDeck", {"deck": deck_name})

    for index, note in enumerate(normalized_notes):
        note_deck = note.deck or args.deck
        note_model = note.model or args.model

        model_fields, canonical_field_map = await _ensure_model_context(note_model)

        fields = anki_services.normalize_and_validate_note_fields(note.fields, model_fields)

        await anki_services.process_data_urls_in_fields(fields, results, index)

        for img in note.images:
            ext_hint: Optional[str] = None
            if img.image_base64:
                try:
                    data_b64, ext_hint = anki_services.sanitize_image_payload(img.image_base64)
                except ValueError as exc:
                    results.append({"index": index, "warn": f"invalid_image_base64: {exc}"})
                    continue
            elif img.image_url:
                try:
                    data_b64 = await anki_services.fetch_image_as_base64(str(img.image_url), img.max_side)
                except Exception as exc:
                    results.append({"index": index, "warn": f"fetch_image_failed: {exc}"})
                    continue
            else:
                results.append({"index": index, "warn": "no_image_provided"})
                continue

            filename = img.filename or f"{uuid.uuid4().hex}.{ext_hint or 'jpg'}"
            canonical_target = canonical_field_map.get(img.target_field.lower())
            if not canonical_target:
                allowed_fields = ", ".join(repr(name) for name in model_fields)
                raise ValueError(
                    "Unknown image target field "
                    f"{img.target_field!r} for note index {index}. "
                    f"Allowed fields: [{allowed_fields}]"
                )
            try:
                await anki_services.store_media_file(filename, data_b64)
                previous = fields[canonical_target]
                fields[canonical_target] = anki_services.ensure_img_tag(previous, filename)
            except Exception as exc:
                results.append({"index": index, "warn": f"store_media_failed: {exc}"})

        notes_payload.append(
            {
                "deckName": note_deck,
                "modelName": note_model,
                "fields": fields,
                "tags": note.tags,
                "options": {"allowDuplicate": False},
            }
        )

    try:
        response = await anki_services.anki_call("addNotes", {"notes": notes_payload})
        for idx, note_id in enumerate(response):
            dedup_key = normalized_notes[idx].dedup_key
            if note_id is None:
                skipped += 1
                detail = {"index": idx, "status": "duplicate"}
                if dedup_key is not None:
                    detail["dedup_key"] = dedup_key
                results.append(detail)
            else:
                added += 1
                detail = {"index": idx, "status": "ok", "noteId": note_id}
                if dedup_key is not None:
                    detail["dedup_key"] = dedup_key
                results.append(detail)
    except Exception as exc:
        raise RuntimeError(f"addNotes_failed: {exc}") from exc

    return AddNotesResult(added=added, skipped=skipped, details=results)


__all__ = [
    "add_from_model",
    "add_notes",
    "find_notes",
    "model_info",
    "note_info",
]
