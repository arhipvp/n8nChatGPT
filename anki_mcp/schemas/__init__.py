"""Публичный интерфейс схем MCP-сервера."""

from .actions import InvokeActionArgs
from .images import ImageSpec
from .models import CardTemplateSpec, CreateModelArgs, CreateModelResult
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
    "CardTemplateSpec",
    "CreateModelArgs",
    "CreateModelResult",
    "InvokeActionArgs",
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
