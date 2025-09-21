"""Инструменты MCP, связанные с Anki."""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Mapping, Optional, Tuple, Union

from .. import app
from ..compat import model_validate
from .. import config
from ..schemas import (
    AddNotesArgs,
    AddNotesResult,
    CardTemplateSpec,
    CreateModelArgs,
    CreateModelResult,
    InvokeActionArgs,
    FindNotesArgs,
    FindNotesResponse,
    ModelInfo,
    NOTE_RESERVED_TOP_LEVEL_KEYS,
    NoteInfo,
    NoteInfoArgs,
    NoteInfoResponse,
    NoteInput,
    NoteUpdate,
    UpdateNotesArgs,
    UpdateNotesResult,
)
from ..services import anki as anki_services


def _normalize_template(template: CardTemplateSpec) -> Dict[str, str]:
    return {
        "Name": template.name,
        "Front": template.front,
        "Back": template.back,
    }


@app.tool(name="anki.invoke")
async def invoke_action(args: InvokeActionArgs) -> Any:
    params_payload: Dict[str, Any]
    if args.params is None:
        params_payload = {}
    elif isinstance(args.params, dict):
        params_payload = dict(args.params)
    elif isinstance(args.params, Mapping):
        params_payload = dict(args.params)
    else:
        raise TypeError("params must be a mapping of argument names to values")

    if args.version is None:
        version = 6
    elif isinstance(args.version, bool) or not isinstance(args.version, int):
        raise TypeError("version must be an integer")
    else:
        version = args.version

    payload = {
        "action": args.action,
        "version": version,
        "params": params_payload,
    }

    result = await anki_services.anki_call(
        payload["action"], payload["params"], version=payload["version"]
    )
    return result


@app.tool(name="anki.create_model")
async def create_model(
    args: Union[CreateModelArgs, Mapping[str, Any]]
) -> CreateModelResult:
    if isinstance(args, CreateModelArgs):
        normalized = args
    else:
        try:
            normalized = model_validate(CreateModelArgs, args)
        except Exception as exc:
            raise ValueError(f"Invalid create_model arguments: {exc}") from exc

    reserved = {"modelName", "inOrderFields", "cardTemplates", "css"}
    extra_options = dict(normalized.options)
    for key in extra_options:
        if key in reserved:
            raise ValueError(
                f"options cannot override reserved parameter {key!r}"
            )

    payload = {
        "modelName": normalized.model_name,
        "inOrderFields": normalized.in_order_fields,
        "cardTemplates": [
            _normalize_template(template) for template in normalized.card_templates
        ],
        "css": normalized.css,
    }

    if normalized.is_cloze is not None:
        existing = extra_options.get("isCloze")
        if existing is not None and existing != normalized.is_cloze:
            raise ValueError(
                "is_cloze conflicts with options['isCloze'] value"
            )
        payload["isCloze"] = normalized.is_cloze
        extra_options["isCloze"] = normalized.is_cloze

    payload.update(extra_options)

    anki_response = await anki_services.anki_call("createModel", payload)

    return CreateModelResult(
        model_name=normalized.model_name,
        in_order_fields=normalized.in_order_fields,
        card_templates=list(normalized.card_templates),
        css=normalized.css,
        options=extra_options,
        anki_response=anki_response,
    )


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
async def model_info(model: Optional[str] = None) -> ModelInfo:
    target_model = model or config.DEFAULT_MODEL
    fields, templates, css = await anki_services.get_model_fields_templates(target_model)
    return ModelInfo(model=target_model, fields=fields, templates=templates, styling=css)


@app.tool(name="anki.add_from_model")
async def add_from_model(
    deck: Optional[str] = None,
    model: Optional[str] = None,
    items: Optional[List[Union[NoteInput, Dict[str, str]]]] = None,
) -> AddNotesResult:
    if items is None:
        raise ValueError("items must be provided")

    deck = deck or config.DEFAULT_DECK
    model = model or config.DEFAULT_MODEL

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


@app.tool(name="anki.update_notes")
async def update_notes(args: UpdateNotesArgs) -> UpdateNotesResult:
    note_ids = [note.note_id for note in args.notes]
    raw_notes = await anki_services.anki_call("notesInfo", {"notes": note_ids})
    normalized_notes = anki_services.normalize_notes_info(raw_notes)

    info_by_id: Dict[int, Optional[NoteInfo]] = {}
    for requested_id, note_info in zip(note_ids, normalized_notes):
        info_by_id[requested_id] = note_info

    model_fields_cache: Dict[str, List[str]] = {}
    canonical_field_cache: Dict[str, Dict[str, str]] = {}

    updated = 0
    skipped = 0
    details: List[dict] = []

    for index, update in enumerate(args.notes):
        detail_logs: List[dict] = []
        detail: Dict[str, Any] = {"index": index, "noteId": update.note_id}

        info = info_by_id.get(update.note_id)
        if info is None:
            detail["status"] = "not_found"
            skipped += 1
            details.append(detail)
            continue

        model_name = info.model_name or ""
        deck_name = info.deck_name or ""
        detail["model"] = model_name
        detail["deck"] = deck_name

        if model_name:
            model_fields = model_fields_cache.get(model_name)
            if model_fields is None:
                if info.fields:
                    model_fields = list(info.fields.keys())
                else:
                    model_fields = await anki_services.get_model_field_names(model_name)
                model_fields_cache[model_name] = model_fields
            canonical_field_map = canonical_field_cache.setdefault(
                model_name, {field.lower(): field for field in model_fields}
            )
        else:
            model_fields = list(info.fields.keys()) if info.fields else []
            canonical_field_map = {
                field.lower(): field for field in model_fields
            }
            canonical_field_cache.setdefault(model_name, canonical_field_map)

        fields_payload: Dict[str, str] = {}
        updated_fields: List[str] = []

        if update.fields:
            raw_fields: Dict[str, str] = {}
            for raw_key, raw_value in update.fields.items():
                if isinstance(raw_value, Mapping) and "value" in raw_value:
                    candidate = raw_value.get("value")
                else:
                    candidate = raw_value

                if candidate is None:
                    normalized_value = ""
                elif isinstance(candidate, str):
                    normalized_value = candidate
                else:
                    normalized_value = str(candidate)

                raw_fields[str(raw_key)] = normalized_value

            normalized, matched_count, unknown_fields = (
                anki_services.normalize_fields_for_model(raw_fields, model_fields)
            )

            if unknown_fields:
                detail["status"] = "error"
                detail["error"] = {
                    "type": "unknown_fields",
                    "fields": unknown_fields,
                }
                skipped += 1
                details.append(detail)
                continue

            if matched_count == 0:
                detail["status"] = "noop"
                detail_logs.append({
                    "index": index,
                    "warn": "no_matching_fields",
                })
            else:
                for original_key, value in raw_fields.items():
                    canonical = canonical_field_map.get(original_key.lower())
                    if canonical:
                        fields_payload[canonical] = normalized.get(canonical, value)
                        updated_fields.append(canonical)

        await anki_services.process_data_urls_in_fields(
            fields_payload, detail_logs, index
        )

        for img in update.images:
            ext_hint: Optional[str] = None
            if img.image_base64:
                try:
                    data_b64, ext_hint = anki_services.sanitize_image_payload(
                        img.image_base64
                    )
                except ValueError as exc:
                    detail_logs.append(
                        {
                            "index": index,
                            "warn": f"invalid_image_base64: {exc}",
                        }
                    )
                    continue
            elif img.image_url:
                try:
                    data_b64 = await anki_services.fetch_image_as_base64(
                        str(img.image_url), img.max_side
                    )
                except Exception as exc:  # pragma: no cover - network failures
                    detail_logs.append(
                        {"index": index, "warn": f"fetch_image_failed: {exc}"}
                    )
                    continue
            else:
                detail_logs.append({"index": index, "warn": "no_image_provided"})
                continue

            filename = img.filename or f"{uuid.uuid4().hex}.{ext_hint or 'jpg'}"
            canonical_target = canonical_field_map.get(img.target_field.lower())
            if not canonical_target:
                detail_logs.append(
                    {
                        "index": index,
                        "warn": "unknown_target_field",
                        "field": img.target_field,
                    }
                )
                continue

            previous = fields_payload.get(
                canonical_target,
                (info.fields or {}).get(canonical_target, ""),
            )
            try:
                await anki_services.store_media_file(filename, data_b64)
                fields_payload[canonical_target] = anki_services.ensure_img_tag(
                    previous, filename
                )
                updated_fields.append(canonical_target)
            except Exception as exc:  # pragma: no cover - error path
                detail_logs.append(
                    {"index": index, "warn": f"store_media_failed: {exc}"}
                )

        operations_performed = False

        try:
            if fields_payload:
                await anki_services.anki_call(
                    "updateNoteFields",
                    {"note": {"id": update.note_id, "fields": fields_payload}},
                )
                operations_performed = True

            if update.add_tags:
                tags_payload = " ".join(update.add_tags)
                await anki_services.anki_call(
                    "addTags", {"notes": [update.note_id], "tags": tags_payload}
                )
                detail["addedTags"] = update.add_tags
                operations_performed = True

            if update.remove_tags:
                tags_payload = " ".join(update.remove_tags)
                await anki_services.anki_call(
                    "removeTags",
                    {"notes": [update.note_id], "tags": tags_payload},
                )
                detail["removedTags"] = update.remove_tags
                operations_performed = True

            if update.deck and update.deck != deck_name:
                cards = info.cards or []
                if cards:
                    await anki_services.anki_call(
                        "changeDeck", {"cards": cards, "deck": update.deck}
                    )
                    detail["deckChangedTo"] = update.deck
                    operations_performed = True
                else:
                    detail_logs.append(
                        {"index": index, "warn": "no_cards_for_deck_change"}
                    )
        except Exception as exc:
            detail["status"] = "error"
            detail["error"] = str(exc)
            skipped += 1
            if detail_logs:
                detail["logs"] = detail_logs
            if updated_fields:
                detail["updatedFields"] = sorted(set(updated_fields))
            details.append(detail)
            continue

        if updated_fields:
            detail["updatedFields"] = sorted(set(updated_fields))

        if detail_logs:
            detail["logs"] = detail_logs

        if operations_performed:
            detail["status"] = "ok"
            updated += 1
        else:
            detail["status"] = detail.get("status", "noop")
            skipped += 1

        details.append(detail)

    return UpdateNotesResult(updated=updated, skipped=skipped, details=details)


__all__ = [
    "invoke_action",
    "add_from_model",
    "add_notes",
    "create_model",
    "find_notes",
    "model_info",
    "note_info",
    "update_notes",
]
