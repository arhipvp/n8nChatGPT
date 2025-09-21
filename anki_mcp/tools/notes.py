"""Инструменты Anki, связанные с заметками и карточками."""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from typing import Any, Dict, List, Mapping, Optional, Tuple, Union

from .. import app, config
from ..compat import model_validate
from ..schemas import (
    AddNotesArgs,
    AddNotesResult,
    CardInfo,
    CardsInfoArgs,
    CardsToNotesArgs,
    CardsToNotesResponse,
    DeleteNotesArgs,
    DeleteNotesResult,
    FindCardsArgs,
    FindCardsResponse,
    FindNotesArgs,
    FindNotesResponse,
    NOTE_RESERVED_TOP_LEVEL_KEYS,
    NoteInfo,
    NoteInfoArgs,
    NoteInfoResponse,
    NoteInput,
    NoteUpdate,
    NotesToCardsArgs,
    NotesToCardsResponse,
    UpdateNotesArgs,
    UpdateNotesResult,
)
from ..services import anki as anki_services
from ..services import client as anki_client
from ..services import media as media_services
from ..services import notes as notes_services


@app.tool(name="anki.find_notes")
async def find_notes(args: FindNotesArgs) -> FindNotesResponse:
    raw_note_ids = await anki_client.anki_call("findNotes", {"query": args.query})
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
        raw_notes = await anki_client.anki_call("notesInfo", {"notes": normalized_ids})
        notes = notes_services.normalize_notes_info(raw_notes)

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

    raw_card_ids = await anki_client.anki_call(
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


@app.tool(name="anki.cards_info")
async def cards_info(
    args: Union[CardsInfoArgs, Mapping[str, Any]]
) -> List[CardInfo]:
    if isinstance(args, CardsInfoArgs):
        normalized = args
    else:
        try:
            normalized = model_validate(CardsInfoArgs, args)
        except Exception as exc:
            raise ValueError(f"Invalid cards_info arguments: {exc}") from exc

    raw_cards = await anki_client.anki_call(
        "cardsInfo", {"cards": normalized.card_ids}
    )
    if not isinstance(raw_cards, list):
        raise ValueError("cardsInfo response must be a list of card objects")

    normalized_cards: List[CardInfo] = []
    for index, raw_card in enumerate(raw_cards):
        if not isinstance(raw_card, Mapping):
            raise ValueError(
                f"cardsInfo returned non-object entry at index {index}: {raw_card!r}"
            )
        try:
            normalized_cards.append(model_validate(CardInfo, raw_card))
        except Exception as exc:
            raise ValueError(
                f"cardsInfo returned invalid card at index {index}: {exc}"
            ) from exc

    return normalized_cards


@app.tool(name="anki.cards_to_notes")
async def cards_to_notes(
    args: Union[CardsToNotesArgs, Mapping[str, Any]]
) -> CardsToNotesResponse:
    if isinstance(args, CardsToNotesArgs):
        normalized = args
    else:
        try:
            normalized = model_validate(CardsToNotesArgs, args)
        except Exception as exc:
            raise ValueError(f"Invalid cards_to_notes arguments: {exc}") from exc

    raw_response = await anki_client.anki_call(
        "cardsToNotes", {"cards": normalized.card_ids}
    )

    mapping: Dict[int, int]
    if isinstance(raw_response, Mapping):
        mapping = {}
        for index, (raw_card_id, raw_note_id) in enumerate(raw_response.items()):
            if isinstance(raw_card_id, bool):
                raise ValueError(
                    "cardsToNotes returned boolean card identifier"
                )
            if isinstance(raw_note_id, bool):
                raise ValueError(
                    "cardsToNotes returned boolean note identifier"
                )
            try:
                card_id = int(raw_card_id)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    "cardsToNotes returned non-integer card identifier"
                ) from exc
            try:
                note_id = int(raw_note_id)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    "cardsToNotes returned non-integer note identifier"
                ) from exc
            mapping[card_id] = note_id
    elif isinstance(raw_response, Iterable) and not isinstance(
        raw_response, (str, bytes)
    ):
        try:
            note_ids = list(raw_response)
        except TypeError as exc:  # pragma: no cover - safety guard
            raise ValueError("cardsToNotes response must be iterable") from exc
        if len(note_ids) != len(normalized.card_ids):
            raise ValueError(
                "cardsToNotes response length does not match requested card ids"
            )
        mapping = {}
        for index, raw_note_id in enumerate(note_ids):
            if isinstance(raw_note_id, bool):
                raise ValueError(
                    f"cardsToNotes returned boolean note id at index {index}: {raw_note_id!r}"
                )
            try:
                note_id = int(raw_note_id)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"cardsToNotes returned non-integer note id at index {index}: {raw_note_id!r}"
                ) from exc
            mapping[normalized.card_ids[index]] = note_id
    else:
        raise ValueError("cardsToNotes response must be a mapping or list of note ids")

    try:
        return model_validate(
            CardsToNotesResponse, {"cards_to_notes": mapping}
        )
    except Exception as exc:  # pragma: no cover - should not trigger with sanitized mapping
        raise ValueError(f"cardsToNotes response could not be validated: {exc}") from exc


@app.tool(name="anki.notes_to_cards")
async def notes_to_cards(
    args: Union[NotesToCardsArgs, Mapping[str, Any]]
) -> NotesToCardsResponse:
    if isinstance(args, NotesToCardsArgs):
        normalized = args
    else:
        try:
            normalized = model_validate(NotesToCardsArgs, args)
        except Exception as exc:
            raise ValueError(f"Invalid notes_to_cards arguments: {exc}") from exc

    raw_response = await anki_client.anki_call(
        "notesToCards", {"notes": normalized.note_ids}
    )

    def _normalize_cards(raw_cards: Any, note_id: int) -> List[int]:
        if raw_cards is None:
            return []

        if isinstance(raw_cards, Mapping):
            candidates = raw_cards.values()
        else:
            candidates = raw_cards

        if isinstance(candidates, (str, bytes)):
            raise ValueError(
                f"notesToCards returned invalid card ids for note {note_id}"
            )

        if not isinstance(candidates, Iterable):
            raise ValueError(
                f"notesToCards returned invalid card ids for note {note_id}"
            )

        normalized_cards: List[int] = []
        for index, raw_card_id in enumerate(candidates):
            if isinstance(raw_card_id, bool):
                raise ValueError(
                    "notesToCards returned boolean card identifier"
                )
            try:
                card_id = int(raw_card_id)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    "notesToCards returned non-integer card identifier"
                ) from exc
            normalized_cards.append(card_id)

        return normalized_cards

    mapping: Dict[int, List[int]]
    if isinstance(raw_response, Mapping):
        mapping = {}
        for raw_note_id, raw_cards in raw_response.items():
            if isinstance(raw_note_id, bool):
                raise ValueError("notesToCards returned boolean note identifier")
            try:
                note_id = int(raw_note_id)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    "notesToCards returned non-integer note identifier"
                ) from exc
            mapping[note_id] = _normalize_cards(raw_cards, note_id)
    elif isinstance(raw_response, Iterable) and not isinstance(
        raw_response, (str, bytes)
    ):
        try:
            card_groups = list(raw_response)
        except TypeError as exc:  # pragma: no cover - safety guard
            raise ValueError("notesToCards response must be iterable") from exc
        if len(card_groups) != len(normalized.note_ids):
            raise ValueError(
                "notesToCards response length does not match requested note ids"
            )
        mapping = {}
        for index, raw_cards in enumerate(card_groups):
            note_id = normalized.note_ids[index]
            mapping[note_id] = _normalize_cards(raw_cards, note_id)
    else:
        raise ValueError(
            "notesToCards response must be a mapping or list of card id sequences"
        )

    try:
        return model_validate(
            NotesToCardsResponse, {"notes_to_cards": mapping}
        )
    except Exception as exc:  # pragma: no cover - should not trigger with sanitized mapping
        raise ValueError(f"notesToCards response could not be validated: {exc}") from exc


@app.tool(name="anki.note_info")
async def note_info(args: NoteInfoArgs) -> NoteInfoResponse:
    raw_notes = await anki_client.anki_call("notesInfo", {"notes": args.note_ids})
    normalized = notes_services.normalize_notes_info(raw_notes)
    return NoteInfoResponse(notes=normalized)


@app.tool(name="anki.add_from_model")
async def add_from_model(
    deck: Optional[str] = None,
    model: Optional[str] = None,
    items: Optional[List[Union[NoteInput, Dict[str, Any]]]] = None,
) -> AddNotesResult:
    if items is None:
        raise ValueError("items must be provided")

    deck = deck or config.DEFAULT_DECK
    model = model or config.DEFAULT_MODEL

    await anki_client.anki_call("createDeck", {"deck": deck})

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
    canonical_field_map_cache: Dict[str, Dict[str, str]] = {}

    async def _ensure_model_context_local(
        model_name: str,
    ) -> Tuple[List[str], Dict[str, str]]:
        return await _ensure_model_context(
            model_name, model_fields_cache, canonical_field_map_cache
        )

    for note in normalized_items:
        if note.deck:
            decks_to_create.add(note.deck)

    for deck_name in decks_to_create:
        await anki_client.anki_call("createDeck", {"deck": deck_name})

    results: List[dict] = []
    added = skipped = 0

    notes_payload: List[dict] = []
    for index, note in enumerate(normalized_items):
        note_deck = note.deck or deck
        note_model = note.model or model

        model_fields, canonical_field_map = await _ensure_model_context_local(
            note_model
        )

        fields = notes_services.normalize_and_validate_note_fields(note.fields, model_fields)

        for field_name, value in list(fields.items()):
            if field_name.lower() == "sources":
                fields[field_name] = media_services.auto_link_urls(value)

        await media_services.process_data_urls_in_fields(fields, results, index)

        for img in note.images:
            ext_hint: Optional[str] = None
            if img.image_base64:
                try:
                    data_b64, ext_hint = media_services.sanitize_image_payload(img.image_base64)
                except ValueError as exc:
                    results.append({"index": index, "warn": f"invalid_image_base64: {exc}"})
                    continue
            elif img.image_url:
                try:
                    data_b64 = await media_services.fetch_image_as_base64(str(img.image_url), img.max_side)
                except Exception as exc:
                    results.append({"index": index, "warn": f"fetch_image_failed: {exc}"})
                    continue
            else:
                results.append({"index": index, "warn": "no_image_provided"})
                continue

            filename = img.filename or f"{uuid.uuid4().hex}.{ext_hint or 'jpg'}"
            canonical_target = canonical_field_map.get(img.target_field.lower())
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
                await anki_client.store_media_file(filename, data_b64)
                previous = fields[canonical_target]
                fields[canonical_target] = media_services.ensure_img_tag(previous, filename)
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
        response = await anki_client.anki_call("addNotes", {"notes": notes_payload})
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


async def _ensure_model_context(
    model_name: str,
    model_fields_cache: Dict[str, List[str]],
    canonical_field_map_cache: Dict[str, Dict[str, str]],
) -> Tuple[List[str], Dict[str, str]]:
    cached_fields = model_fields_cache.get(model_name)
    if cached_fields is None:
        fields = await anki_services.get_model_field_names(model_name)
        model_fields_cache[model_name] = fields
        canonical_field_map_cache[model_name] = {
            field.lower(): field for field in fields
        }
    return model_fields_cache[model_name], canonical_field_map_cache[model_name]


@app.tool(name="anki.add_notes")
async def add_notes(args: AddNotesArgs) -> AddNotesResult:
    notes_payload: List[dict] = []
    results: List[dict] = []
    added = skipped = 0
    normalized_notes: List[NoteInput] = list(args.notes)

    decks_to_create = {args.deck}
    model_fields_cache: Dict[str, List[str]] = {}
    canonical_field_map_cache: Dict[str, Dict[str, str]] = {}

    async def _ensure_model_context_local(model_name: str) -> Tuple[List[str], Dict[str, str]]:
        return await _ensure_model_context(model_name, model_fields_cache, canonical_field_map_cache)

    for note in normalized_notes:
        if note.deck:
            decks_to_create.add(note.deck)

    for deck_name in decks_to_create:
        await anki_client.anki_call("createDeck", {"deck": deck_name})

    for index, note in enumerate(normalized_notes):
        note_deck = note.deck or args.deck
        note_model = note.model or args.model

        model_fields, canonical_field_map = await _ensure_model_context_local(note_model)

        fields = notes_services.normalize_and_validate_note_fields(note.fields, model_fields)

        for field_name, value in list(fields.items()):
            if field_name.lower() == "sources":
                fields[field_name] = media_services.auto_link_urls(value)

        await media_services.process_data_urls_in_fields(fields, results, index)

        for img in note.images:
            ext_hint: Optional[str] = None
            if img.image_base64:
                try:
                    data_b64, ext_hint = media_services.sanitize_image_payload(img.image_base64)
                except ValueError as exc:
                    results.append({"index": index, "warn": f"invalid_image_base64: {exc}"})
                    continue
            elif img.image_url:
                try:
                    data_b64 = await media_services.fetch_image_as_base64(str(img.image_url), img.max_side)
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
                await anki_client.store_media_file(filename, data_b64)
                previous = fields[canonical_target]
                fields[canonical_target] = media_services.ensure_img_tag(previous, filename)
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
        response = await anki_client.anki_call("addNotes", {"notes": notes_payload})
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
    raw_notes = await anki_client.anki_call("notesInfo", {"notes": note_ids})
    normalized_notes = notes_services.normalize_notes_info(raw_notes)

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
                notes_services.normalize_fields_for_model(raw_fields, model_fields)
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

        await media_services.process_data_urls_in_fields(
            fields_payload, detail_logs, index
        )

        for img in update.images:
            ext_hint: Optional[str] = None
            if img.image_base64:
                try:
                    data_b64, ext_hint = media_services.sanitize_image_payload(
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
                    data_b64 = await media_services.fetch_image_as_base64(
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
                await anki_client.store_media_file(filename, data_b64)
                fields_payload[canonical_target] = media_services.ensure_img_tag(
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
                await anki_client.anki_call(
                    "updateNoteFields",
                    {"note": {"id": update.note_id, "fields": fields_payload}},
                )
                operations_performed = True

            if update.add_tags:
                tags_payload = " ".join(update.add_tags)
                await anki_client.anki_call(
                    "addTags", {"notes": [update.note_id], "tags": tags_payload}
                )
                detail["addedTags"] = update.add_tags
                operations_performed = True

            if update.remove_tags:
                tags_payload = " ".join(update.remove_tags)
                await anki_client.anki_call(
                    "removeTags",
                    {"notes": [update.note_id], "tags": tags_payload},
                )
                detail["removedTags"] = update.remove_tags
                operations_performed = True

            if update.deck and update.deck != deck_name:
                cards = info.cards or []
                if cards:
                    await anki_client.anki_call(
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
        response = await anki_client.anki_call("deleteNotes", {"notes": note_ids})
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
    "find_notes",
    "find_cards",
    "cards_info",
    "cards_to_notes",
    "notes_to_cards",
    "note_info",
    "add_from_model",
    "add_notes",
    "update_notes",
    "delete_notes",
]
