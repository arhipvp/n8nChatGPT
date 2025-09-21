"""Публичный интерфейс схем MCP-сервера."""

from .actions import InvokeActionArgs
from .decks import DeleteDecksArgs, DeckInfo, ListDecksResponse, RenameDeckArgs
from .images import ImageSpec
from .models import CardTemplateSpec, CreateModelArgs, CreateModelResult
from .notes import (
    AddNotesArgs,
    AddNotesResult,
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


__all__ = [
    "CardTemplateSpec",
    "CreateModelArgs",
    "CreateModelResult",
    "DeckInfo",
    "DeleteDecksArgs",
    "InvokeActionArgs",
    "AddNotesArgs",
    "AddNotesResult",
    "ListDecksResponse",
    "DeleteNotesArgs",
    "DeleteNotesResult",
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
