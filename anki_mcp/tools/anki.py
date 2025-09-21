"""Инструменты MCP, связанные с Anki."""

from __future__ import annotations

import base64
import binascii
import uuid
from typing import Any, Dict, List, Mapping, Optional, Tuple, Union

from .. import app
from ..compat import model_validate
from .. import config
from ..schemas import (
    AddNotesArgs,
    AddNotesResult,
    CreateDeckArgs,
    DeckInfo,
    DeleteDecksArgs,
    DeleteMediaArgs,
    DeleteNotesArgs,
    DeleteNotesResult,
    FindCardsArgs,
    FindCardsResponse,
    MediaRequest,
    MediaResponse,
    StoreMediaArgs,
    CardTemplateSpec,
    CreateModelArgs,
    CreateModelResult,
    ListModelsResponse,
    UpdateModelStylingArgs,
    UpdateModelTemplatesArgs,
    InvokeActionArgs,
    FindNotesArgs,
    FindNotesResponse,
    ListDecksResponse,
    ModelSummary,
    ModelInfo,
    NOTE_RESERVED_TOP_LEVEL_KEYS,
    NoteInfo,
    NoteInfoArgs,
    NoteInfoResponse,
    NoteInput,
    NoteUpdate,
    RenameDeckArgs,
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


def _normalize_media_error(filename: str, exc: Exception) -> Exception:
    message = str(exc)
    lowered = message.lower()
    markers = (
        "not found",
        "does not exist",
        "no such file",
        "missing",
    )
    if any(marker in lowered for marker in markers):
        return FileNotFoundError(f"Media file {filename!r} not found")
    return exc


def _calculate_media_size(data_base64: str) -> Optional[int]:
    try:
        raw = base64.b64decode(data_base64, validate=True)
    except (binascii.Error, ValueError):
        try:
            raw = base64.b64decode(data_base64, validate=False)
        except Exception:
            return None
    return len(raw)


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


@app.tool(name="anki.update_model_templates")
async def update_model_templates(
    args: Union[UpdateModelTemplatesArgs, Mapping[str, Any]]
) -> Any:
    if isinstance(args, UpdateModelTemplatesArgs):
        normalized = args
    else:
        try:
            normalized = model_validate(UpdateModelTemplatesArgs, args)
        except Exception as exc:
            raise ValueError(
                f"Invalid update_model_templates arguments: {exc}"
            ) from exc

    templates_payload: Dict[str, Dict[str, str]] = {}
    for key, template in normalized.templates.items():
        template_name = template.name
        if not template_name:
            raise ValueError("Template name must be a non-empty string")
        key_stripped = key.strip()
        if key_stripped and key_stripped != template_name:
            raise ValueError(
                f"Template mapping key {key!r} must match template name {template_name!r}"
            )
        if template_name in templates_payload:
            raise ValueError(f"Duplicate template definition for {template_name!r}")
        templates_payload[template_name] = {
            "Front": template.front,
            "Back": template.back,
        }

    payload = {
        "model": {
            "name": normalized.model_name,
            "templates": templates_payload,
        }
    }

    return await anki_services.anki_call("updateModelTemplates", payload)


@app.tool(name="anki.update_model_styling")
async def update_model_styling(
    args: Union[UpdateModelStylingArgs, Mapping[str, Any]]
) -> Any:
    if isinstance(args, UpdateModelStylingArgs):
        normalized = args
    else:
        try:
            normalized = model_validate(UpdateModelStylingArgs, args)
        except Exception as exc:
            raise ValueError(
                f"Invalid update_model_styling arguments: {exc}"
            ) from exc

    payload = {
        "model": {
            "name": normalized.model_name,
            "styling": {"css": normalized.css},
        }
    }

    return await anki_services.anki_call("updateModelStyling", payload)


@app.tool(name="anki.list_models")
async def list_models() -> ListModelsResponse:
    raw_models = await anki_services.anki_call("modelNamesAndIds", {})

    if raw_models is None:
        return ListModelsResponse()

    if not isinstance(raw_models, Mapping):
        raise ValueError(
            "modelNamesAndIds response must be a mapping of model names to ids"
        )

    model_summaries: List[ModelSummary] = []
    for name, model_id in raw_models.items():
        if not isinstance(name, str):
            raise ValueError(
                f"modelNamesAndIds returned invalid model name: {name!r}"
            )

        if isinstance(model_id, bool):
            raise ValueError(
                "modelNamesAndIds returned non-integer model id "
                f"for {name!r}: {model_id!r}"
            )

        try:
            normalized_id = int(model_id)
        except (TypeError, ValueError):
            raise ValueError(
                "modelNamesAndIds returned non-integer model id "
                f"for {name!r}: {model_id!r}"
            ) from None

        model_summaries.append(ModelSummary(id=normalized_id, name=name))

    sorted_models = sorted(
        model_summaries, key=lambda model: (model.name.casefold(), model.name)
    )

    return ListModelsResponse(models=sorted_models)


@app.tool(name="anki.list_decks")
async def list_decks() -> List[DeckInfo]:
    raw_decks = await anki_services.anki_call("deckNamesAndIds", {})

    if raw_decks is None:
        return []

    if not isinstance(raw_decks, Mapping):
        raise ValueError("deckNamesAndIds response must be a mapping of deck names to ids")

    deck_infos: List[DeckInfo] = []
    for name, deck_id in raw_decks.items():
        if not isinstance(name, str):
            raise ValueError(f"deckNamesAndIds returned invalid deck name: {name!r}")

        if isinstance(deck_id, bool):
            raise ValueError(
                f"deckNamesAndIds returned non-integer deck id for {name!r}: {deck_id!r}"
            )

        try:
            normalized_id = int(deck_id)
        except (TypeError, ValueError):
            raise ValueError(
                f"deckNamesAndIds returned non-integer deck id for {name!r}: {deck_id!r}"
            ) from None

        deck_infos.append(DeckInfo(id=normalized_id, name=name))

    response = ListDecksResponse(decks=deck_infos)
    return response.decks


@app.tool(name="anki.create_deck")
async def create_deck(
    args: Union[CreateDeckArgs, Mapping[str, Any]]
) -> Any:
    if isinstance(args, CreateDeckArgs):
        normalized = args
    else:
        try:
            normalized = model_validate(CreateDeckArgs, args)
        except Exception as exc:
            raise ValueError(f"Invalid create_deck arguments: {exc}") from exc

    payload = {"deck": normalized.deck}
    return await anki_services.anki_call("createDeck", payload)


@app.tool(name="anki.rename_deck")
async def rename_deck(args: RenameDeckArgs):
    payload = {"oldName": args.old_name, "newName": args.new_name}
    return await anki_services.anki_call("renameDeck", payload)


@app.tool(name="anki.delete_decks")
async def delete_decks(args: DeleteDecksArgs):
    payload = {"decks": list(args.decks), "cardsToo": bool(args.cards_too)}
    return await anki_services.anki_call("deleteDecks", payload)


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


@app.tool(name="anki.find_cards")
async def find_cards(
    args: Union[FindCardsArgs, Mapping[str, Any]]
) -> FindCardsResponse:
    if isinstance(args, FindCardsArgs):
        normalized = args
    else:
        try:
            normalized = model_validate(FindCardsArgs, args)
        except Exception as exc:
            raise ValueError(f"Invalid find_cards arguments: {exc}") from exc

    raw_card_ids = await anki_services.anki_call(
        "findCards", {"query": normalized.query}
    )
    if not isinstance(raw_card_ids, list):
        raise ValueError("findCards response must be a list of card ids")

    normalized_ids: List[int] = []
    for index, raw_id in enumerate(raw_card_ids):
        if isinstance(raw_id, bool):
            raise ValueError(
                f"findCards returned non-integer value at index {index}: {raw_id!r}"
            )
        try:
            card_id = int(raw_id)
        except (TypeError, ValueError):
            raise ValueError(
                f"findCards returned non-integer value at index {index}: {raw_id!r}"
            ) from None
        normalized_ids.append(card_id)

    offset = normalized.offset or 0
    if offset:
        normalized_ids = normalized_ids[offset:]
    if normalized.limit is not None:
        normalized_ids = normalized_ids[: normalized.limit]

    return FindCardsResponse(card_ids=normalized_ids)


@app.tool(name="anki.get_media")
async def get_media(args: MediaRequest) -> MediaResponse:
    try:
        raw_base64 = await anki_services.anki_call(
            "retrieveMediaFile", {"filename": args.filename}
        )
    except Exception as exc:  # pragma: no cover - конкретные ошибки проверяются тестами
        normalized_exc = _normalize_media_error(args.filename, exc)
        if normalized_exc is exc:
            raise
        raise normalized_exc from exc

    if not isinstance(raw_base64, str):
        raise ValueError("retrieveMediaFile response must be a base64 string")

    size_bytes = _calculate_media_size(raw_base64)
    return MediaResponse(
        filename=args.filename,
        data_base64=raw_base64,
        size_bytes=size_bytes,
    )


@app.tool(name="anki.store_media")
async def store_media(
    args: Union[StoreMediaArgs, Mapping[str, Any]]
) -> Dict[str, Any]:
    if isinstance(args, StoreMediaArgs):
        normalized = args
    else:
        try:
            normalized = model_validate(StoreMediaArgs, args)
        except Exception as exc:
            raise ValueError(f"Invalid store_media arguments: {exc}") from exc

    try:
        try:
            base64.b64decode(normalized.data_base64, validate=True)
        except (binascii.Error, ValueError):
            base64.b64decode(normalized.data_base64, validate=False)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("data_base64 must be valid Base64-encoded string") from exc

    anki_response = await anki_services.store_media_file(
        normalized.filename, normalized.data_base64
    )

    return {
        "filename": normalized.filename,
        "anki_response": anki_response,
    }


@app.tool(name="anki.note_info")
async def note_info(args: NoteInfoArgs) -> NoteInfoResponse:
    raw_notes = await anki_services.anki_call("notesInfo", {"notes": args.note_ids})
    normalized = anki_services.normalize_notes_info(raw_notes)
    return NoteInfoResponse(notes=normalized)


@app.tool(name="anki.delete_media")
async def delete_media(args: DeleteMediaArgs) -> Dict[str, Any]:
    try:
        raw_response = await anki_services.anki_call(
            "deleteMediaFile", {"filename": args.filename}
        )
    except Exception as exc:  # pragma: no cover - конкретные ошибки проверяются тестами
        normalized_exc = _normalize_media_error(args.filename, exc)
        if normalized_exc is exc:
            raise
        raise normalized_exc from exc

    deleted: bool
    if isinstance(raw_response, Mapping):
        deleted = bool(raw_response.get("deleted", True))
    elif isinstance(raw_response, list):
        deleted = all(bool(item) for item in raw_response)
    else:
        deleted = raw_response in (None, True)

    return {
        "filename": args.filename,
        "deleted": deleted,
        "anki_response": raw_response,
    }


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

        for field_name, value in list(fields.items()):
            if field_name.lower() == "sources":
                fields[field_name] = anki_services.auto_link_urls(value)

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

        for field_name, value in list(fields.items()):
            if field_name.lower() == "sources":
                fields[field_name] = anki_services.auto_link_urls(value)

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


@app.tool(name="anki.delete_notes")
async def delete_notes(args: DeleteNotesArgs) -> DeleteNotesResult:
    note_ids = list(args.note_ids)
    if not note_ids:
        raise ValueError("note_ids must contain at least one id")

    try:
        response = await anki_services.anki_call("deleteNotes", {"notes": note_ids})
    except Exception as exc:  # pragma: no cover - defensive, exercised via tests with raising mocks
        raise RuntimeError(f"deleteNotes_failed: {exc}") from exc

    deleted = 0
    missing = 0

    def _coerce_count(value: Any) -> int:
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, (int, float)):
            return int(value)
        if value in (None, ""):
            return 0
        try:
            return int(str(value))
        except (TypeError, ValueError):
            return 1

    def _consume(item: Any) -> None:
        nonlocal deleted, missing

        if item is None:
            return

        if isinstance(item, Mapping):
            results = item.get("results")
            if isinstance(results, (list, tuple, set)):
                for sub in results:
                    _consume(sub)

            notes = item.get("notes")
            if isinstance(notes, (list, tuple, set)):
                for sub in notes:
                    _consume(sub)

            if "deleted" in item:
                deleted += max(_coerce_count(item.get("deleted")), 0)
            if "success" in item:
                deleted += max(_coerce_count(item.get("success")), 0)
            if "removed" in item:
                deleted += max(_coerce_count(item.get("removed")), 0)

            if "missing" in item:
                missing += max(_coerce_count(item.get("missing")), 0)
            if "skipped" in item:
                missing += max(_coerce_count(item.get("skipped")), 0)
            if "failed" in item:
                missing += max(_coerce_count(item.get("failed")), 0)
            if "notFound" in item:
                missing += max(_coerce_count(item.get("notFound")), 0)
            if "not_found" in item:
                missing += max(_coerce_count(item.get("not_found")), 0)

            status = item.get("status")
            if isinstance(status, str):
                lowered = status.lower()
                if lowered in {"ok", "deleted", "success"}:
                    deleted += 1
                elif lowered in {"missing", "skipped", "not_found", "notfound", "failed"}:
                    missing += 1

            return

        if isinstance(item, (list, tuple, set)):
            for sub in item:
                _consume(sub)
            return

        if isinstance(item, bool):
            if item:
                deleted += 1
            else:
                missing += 1
            return

        if isinstance(item, (int, float)):
            count = int(item)
            if count > 0:
                deleted += count
            elif count < 0:
                missing += abs(count)
            return

        if isinstance(item, str):
            if item.strip():
                deleted += 1
            else:
                missing += 1
            return

        if item:
            deleted += 1
        else:
            missing += 1

    if response is None:
        deleted = len(note_ids)
    else:
        _consume(response)

    if deleted < 0:
        deleted = 0
    if missing < 0:
        missing = 0

    processed = deleted + missing
    if processed < len(note_ids):
        missing += len(note_ids) - processed
    elif processed > len(note_ids):
        overflow = processed - len(note_ids)
        if missing >= overflow:
            missing -= overflow
        else:
            deleted = max(deleted - (overflow - missing), 0)
            missing = 0

    return DeleteNotesResult(deleted=deleted, missing=missing)


__all__ = [
    "invoke_action",
    "add_from_model",
    "add_notes",
    "create_model",
    "update_model_templates",
    "delete_decks",
    "delete_media",
    "delete_notes",
    "find_notes",
    "get_media",
    "list_decks",
    "model_info",
    "note_info",
    "rename_deck",
    "update_notes",
]
