"""Публичный интерфейс схем MCP-сервера."""

from .actions import InvokeActionArgs
from .decks import (
    CreateDeckArgs,
    DeleteDecksArgs,
    DeckInfo,
    ListDecksResponse,
    RenameDeckArgs,
)
from .images import ImageSpec
from .media import DeleteMediaArgs as _DeleteMediaArgs
from .media import MediaRequest, MediaResponse, StoreMediaArgs
from .models import (
    CardTemplateSpec,
    CreateModelArgs,
    CreateModelResult,
    ListModelsResponse,
    ModelSummary,
    UpdateModelStylingArgs,
    UpdateModelTemplatesArgs,
)
from .notes import (
    AddNotesArgs,
    AddNotesResult,
    FindCardsArgs,
    FindCardsResponse,
    DeleteNotesArgs,
    DeleteNotesResult,
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
from .search import SearchRequest, SearchResponse, SearchResult


DeleteMediaArgs = _DeleteMediaArgs


__all__ = [
    "CardTemplateSpec",
    "CreateModelArgs",
    "CreateModelResult",
    "CreateDeckArgs",
    "ListModelsResponse",
    "ModelSummary",
    "UpdateModelStylingArgs",
    "UpdateModelTemplatesArgs",
    "DeleteMediaArgs",
    "DeckInfo",
    "DeleteDecksArgs",
    "MediaRequest",
    "MediaResponse",
    "StoreMediaArgs",
    "InvokeActionArgs",
    "AddNotesArgs",
    "AddNotesResult",
    "ListDecksResponse",
    "DeleteNotesArgs",
    "DeleteNotesResult",
    "FindCardsArgs",
    "FindCardsResponse",
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
    "SearchRequest",
    "SearchResponse",
    "SearchResult",
    "UpdateNotesArgs",
    "UpdateNotesResult",
]
