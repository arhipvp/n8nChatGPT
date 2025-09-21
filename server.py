"""Тонкий фасад для обеспечения обратной совместимости с тестами."""

from __future__ import annotations

import uuid

from anki_mcp import (
    AddNotesArgs,
    AddNotesResult,
    DeleteDecksArgs,
    DeleteMediaArgs,
    DeleteNotesArgs,
    DeleteNotesResult,
    DeckInfo,
    CardTemplateSpec,
    CreateDeckArgs,
    CreateModelArgs,
    CreateModelResult,
    UpdateModelStylingArgs,
    UpdateModelTemplatesArgs,
    InvokeActionArgs,
    FindNotesArgs,
    FindNotesResponse,
    ImageSpec,
    ListDecksResponse,
    ListModelsResponse,
    MediaRequest,
    MediaResponse,
    StoreMediaArgs,
    ModelInfo,
    ModelSummary,
    NOTE_RESERVED_TOP_LEVEL_KEYS,
    NoteInfo,
    NoteInfoArgs,
    NoteInfoResponse,
    NoteInput,
    NoteUpdate,
    RenameDeckArgs,
    SearchRequest,
    SearchResponse,
    SearchResult,
    UpdateNotesArgs,
    UpdateNotesResult,
    _build_manifest,
    _env_default,
    _env_optional,
    _manifest_response,
    _normalize_manifest,
    app,
    read_root,
    read_well_known_manifest,
)
from anki_mcp import config as _config
from anki_mcp.actions import search
from anki_mcp.manifest import _format_mcp_info
from anki_mcp.services import anki as anki_services
from anki_mcp.services import search as search_services
from anki_mcp.tools import (
    add_from_model,
    add_notes,
    create_model,
    create_deck,
    delete_decks,
    delete_media,
    delete_notes,
    find_notes,
    get_media,
    invoke_action,
    list_decks,
    list_models,
    model_info,
    note_info,
    rename_deck,
    store_media,
    update_model_styling,
    update_model_templates,
    update_notes,
)
from anki_mcp.tools.misc import greet

_config.reload_from_env()

_CONFIG_EXPORTS = {
    "DEFAULT_DECK",
    "DEFAULT_MODEL",
    "SEARCH_API_URL",
    "SEARCH_API_KEY",
    "ENVIRONMENT_INFO",
    "ANKI_URL",
}


def __getattr__(name: str):
    if name in _CONFIG_EXPORTS:
        return getattr(_config, name)
    raise AttributeError(f"module 'server' has no attribute {name!r}")


def __dir__():
    return sorted(set(globals()) | _CONFIG_EXPORTS)

# Обеспечиваем доступ к httpx для тестовых заглушек.
httpx = search_services.httpx

# Переэкспорт сервисных функций, если они использовались напрямую.
anki_call = anki_services.anki_call
store_media_file = anki_services.store_media_file
fetch_image_as_base64 = anki_services.fetch_image_as_base64
normalize_fields_for_model = anki_services.normalize_fields_for_model
normalize_and_validate_note_fields = anki_services.normalize_and_validate_note_fields
process_data_urls_in_fields = anki_services.process_data_urls_in_fields
sanitize_image_payload = anki_services.sanitize_image_payload
ensure_img_tag = anki_services.ensure_img_tag
build_img_tag = anki_services.build_img_tag
normalize_notes_info = anki_services.normalize_notes_info
get_model_fields_templates = anki_services.get_model_fields_templates
get_model_field_names = anki_services.get_model_field_names

__all__ = [
    "ANKI_URL",
    "DEFAULT_DECK",
    "DEFAULT_MODEL",
    "ENVIRONMENT_INFO",
    "SEARCH_API_KEY",
    "SEARCH_API_URL",
    "AddNotesArgs",
    "AddNotesResult",
    "DeleteDecksArgs",
    "DeleteMediaArgs",
    "DeleteNotesArgs",
    "DeleteNotesResult",
    "DeckInfo",
    "CardTemplateSpec",
    "CreateDeckArgs",
    "CreateModelArgs",
    "CreateModelResult",
    "UpdateModelStylingArgs",
    "UpdateModelTemplatesArgs",
    "InvokeActionArgs",
    "FindNotesArgs",
    "FindNotesResponse",
    "ImageSpec",
    "ListDecksResponse",
    "ListModelsResponse",
    "MediaRequest",
    "MediaResponse",
    "StoreMediaArgs",
    "ModelInfo",
    "ModelSummary",
    "NOTE_RESERVED_TOP_LEVEL_KEYS",
    "NoteInfo",
    "NoteInfoArgs",
    "NoteInfoResponse",
    "NoteInput",
    "NoteUpdate",
    "RenameDeckArgs",
    "SearchRequest",
    "SearchResponse",
    "SearchResult",
    "UpdateNotesArgs",
    "UpdateNotesResult",
    "_build_manifest",
    "_env_default",
    "_env_optional",
    "_format_mcp_info",
    "_manifest_response",
    "_normalize_manifest",
    "add_from_model",
    "add_notes",
    "create_deck",
    "create_model",
    "update_model_styling",
    "update_model_templates",
    "delete_decks",
    "delete_media",
    "delete_notes",
    "invoke_action",
    "anki_call",
    "app",
    "uuid",
    "build_img_tag",
    "ensure_img_tag",
    "fetch_image_as_base64",
    "find_notes",
    "get_media",
    "get_model_field_names",
    "get_model_fields_templates",
    "greet",
    "list_decks",
    "list_models",
    "httpx",
    "model_info",
    "normalize_and_validate_note_fields",
    "normalize_fields_for_model",
    "normalize_notes_info",
    "note_info",
    "process_data_urls_in_fields",
    "read_root",
    "read_well_known_manifest",
    "sanitize_image_payload",
    "search",
    "rename_deck",
    "store_media",
    "store_media_file",
    "update_notes",
]
