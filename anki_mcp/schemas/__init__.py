"""Публичный интерфейс схем MCP-сервера."""

from .images import ImageSpec
from .notes import (
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
    NoteUpdate,
    UpdateNotesArgs,
    UpdateNotesResult,
)
from .search import SearchRequest, SearchResponse, SearchResult


__all__ = [
    "AddNotesArgs",
    "AddNotesResult",
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
]
