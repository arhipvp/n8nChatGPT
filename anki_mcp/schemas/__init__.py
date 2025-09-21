"""Публичный интерфейс схем MCP-сервера."""

from .actions import InvokeActionArgs
from .decks import (
    CreateDeckArgs,
    DeleteDecksArgs,
    DeckInfo,
    DeckConfig,
    DeckLapseOptions,
    DeckNewOptions,
    DeckRevOptions,
    GetDeckConfigArgs,
    ListDecksResponse,
    RenameDeckArgs,
    SaveDeckConfigArgs,
)
from .cards import CardInfo, CardsInfoArgs, CardsToNotesArgs, CardsToNotesResponse
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
from .tags import ListTagsResponse as _ListTagsResponse, TagsList


DeleteMediaArgs = _DeleteMediaArgs
ListTagsResponse = _ListTagsResponse


__all__ = [
    "CardInfo",
    "CardsInfoArgs",
    "CardsToNotesArgs",
    "CardsToNotesResponse",
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
    "DeckConfig",
    "DeleteDecksArgs",
    "DeckLapseOptions",
    "DeckNewOptions",
    "DeckRevOptions",
    "MediaRequest",
    "MediaResponse",
    "StoreMediaArgs",
    "InvokeActionArgs",
    "AddNotesArgs",
    "AddNotesResult",
    "ListDecksResponse",
    "DeleteNotesArgs",
    "DeleteNotesResult",
    "GetDeckConfigArgs",
    "FindCardsArgs",
    "FindCardsResponse",
    "FindNotesArgs",
    "FindNotesResponse",
    "ImageSpec",
    "ListTagsResponse",
    "ModelInfo",
    "NOTE_RESERVED_TOP_LEVEL_KEYS",
    "NoteInfo",
    "NoteInfoArgs",
    "NoteInfoResponse",
    "NoteInput",
    "NoteUpdate",
    "SaveDeckConfigArgs",
    "RenameDeckArgs",
    "SearchRequest",
    "SearchResponse",
    "SearchResult",
    "TagsList",
    "UpdateNotesArgs",
    "UpdateNotesResult",
]
