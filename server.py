"""Тонкий фасад для обеспечения обратной совместимости с тестами."""

from __future__ import annotations

import uuid

from anki_mcp import (
    AddNotesArgs,
    AddNotesResult,
    CardTemplateSpec,
    CreateModelArgs,
    CreateModelResult,
    FindNotesArgs,
    FindNotesResponse,
    ImageSpec,
    ModelInfo,
    NOTE_RESERVED_TOP_LEVEL_KEYS,
    NoteInfo,
    NoteInfoArgs,
    NoteInfoResponse,
    NoteInput,
    NoteUpdate,
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
    find_notes,
    model_info,
    note_info,
    update_notes,
)
from anki_mcp.tools.misc import greet

_config.reload_from_env()

DEFAULT_DECK = _config.DEFAULT_DECK
DEFAULT_MODEL = _config.DEFAULT_MODEL
SEARCH_API_URL = _config.SEARCH_API_URL
SEARCH_API_KEY = _config.SEARCH_API_KEY
ENVIRONMENT_INFO = _config.ENVIRONMENT_INFO
ANKI_URL = _config.ANKI_URL

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
    "CardTemplateSpec",
    "CreateModelArgs",
    "CreateModelResult",
    "FindNotesArgs",
    "FindNotesResponse",
    "ImageSpec",
    "ModelInfo",
    "NOTE_RESERVED_TOP_LEVEL_KEYS",
    "NoteInfo",
    "NoteInfoArgs",
    "NoteInfoResponse",
    "NoteInput",
    "NoteUpdate",
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
    "create_model",
    "anki_call",
    "app",
    "uuid",
    "build_img_tag",
    "ensure_img_tag",
    "fetch_image_as_base64",
    "find_notes",
    "get_model_field_names",
    "get_model_fields_templates",
    "greet",
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
    "store_media_file",
    "update_notes",
]
