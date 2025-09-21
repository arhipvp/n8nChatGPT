"""Основной пакет MCP-сервера Anki."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastmcp import FastMCP


# Инициализация FastMCP-приложения доступна для импорта из пакета.
app = FastMCP("anki-mcp")

if not hasattr(app, "action"):
    setattr(app, "action", app.tool)


from . import actions  # noqa: E402 - регистрация действий
from . import tools  # noqa: E402 - регистрация инструментов
from . import config as _config
from .config import _env_default, _env_optional

if TYPE_CHECKING:  # pragma: no cover - подсказки типов при статическом анализе
    from .config import (
        ANKI_URL,
        DEFAULT_DECK,
        DEFAULT_MODEL,
        ENVIRONMENT_INFO,
        SEARCH_API_KEY,
        SEARCH_API_URL,
    )
from .manifest import (
    _build_manifest,
    _manifest_response,
    _normalize_manifest,
    read_root,
    read_well_known_manifest,
)
from .schemas import (
    AddNotesArgs,
    AddNotesResult,
    CardTemplateSpec,
    CreateModelArgs,
    CreateModelResult,
    DeckInfo,
    DeleteDecksArgs,
    DeleteNotesArgs,
    DeleteNotesResult,
    FindNotesArgs,
    FindNotesResponse,
    ImageSpec,
    InvokeActionArgs,
    ListDecksResponse,
    ModelInfo,
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
)


__all__ = [
    "AddNotesArgs",
    "AddNotesResult",
    "CardTemplateSpec",
    "CreateModelArgs",
    "CreateModelResult",
    "DeckInfo",
    "DeleteDecksArgs",
    "DeleteNotesArgs",
    "DeleteNotesResult",
    "InvokeActionArgs",
    "ANKI_URL",
    "DEFAULT_DECK",
    "DEFAULT_MODEL",
    "ENVIRONMENT_INFO",
    "ListDecksResponse",
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
    "RenameDeckArgs",
    "SEARCH_API_KEY",
    "SEARCH_API_URL",
    "SearchRequest",
    "SearchResponse",
    "SearchResult",
    "UpdateNotesArgs",
    "UpdateNotesResult",
    "_build_manifest",
    "_env_default",
    "_env_optional",
    "_manifest_response",
    "_normalize_manifest",
    "app",
    "read_root",
    "read_well_known_manifest",
]


_CONFIG_EXPORTS = {
    "DEFAULT_DECK",
    "DEFAULT_MODEL",
    "ENVIRONMENT_INFO",
    "SEARCH_API_URL",
    "SEARCH_API_KEY",
    "ANKI_URL",
}


def __getattr__(name: str):
    if name in _CONFIG_EXPORTS:
        return getattr(_config, name)
    raise AttributeError(f"module 'anki_mcp' has no attribute {name!r}")


def __dir__():
    return sorted(set(globals()) | _CONFIG_EXPORTS)
