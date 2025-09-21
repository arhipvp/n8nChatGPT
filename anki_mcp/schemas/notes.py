"""Pydantic-схемы для заметок Anki."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any, Dict, List, Optional

from ..compat import (
    BaseModel,
    ConfigDict,
    Field,
    constr,
    field_validator,
    model_validator,
    root_validator,
    validator,
)
from .. import config
from .images import ImageSpec


NOTE_RESERVED_TOP_LEVEL_KEYS = {
    "tags",
    "images",
    "dedup_key",
    "deck",
    "model",
    "deckName",
    "modelName",
}


def _coerce_note_fields(cls, values):
    """Извлекает плоские поля в NoteInput.fields до стандартной валидации."""

    if not isinstance(values, dict):  # pragma: no cover - для совместимости с Pydantic v1
        return values

    if "fields" in values:
        return values

    candidate_items = {
        key: values[key]
        for key in list(values.keys())
        if key not in NOTE_RESERVED_TOP_LEVEL_KEYS
    }

    if not candidate_items:
        raise ValueError(
            "Каждый элемент items должен содержать объект fields с полями заметки"
        )

    normalized = {k: v for k, v in values.items() if k not in candidate_items}
    normalized["fields"] = candidate_items
    return normalized


def _normalize_note_input_tags(raw_tags: Any) -> List[str]:
    if raw_tags is None:
        return []

    normalized: List[str] = []

    def _consume(value: Any) -> None:
        if value is None:
            return

        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return
            for part in re.split(r"[,\s]+", stripped):
                if part:
                    normalized.append(part)
            return

        if isinstance(value, Mapping):
            for sub_value in value.values():
                _consume(sub_value)
            return

        if isinstance(value, Iterable):
            for item in value:
                _consume(item)
            return

        text = str(value).strip()
        if text:
            normalized.append(text)

    _consume(raw_tags)
    return normalized


class NoteInput(BaseModel):
    fields: Dict[str, str]
    tags: List[str] = Field(default_factory=list)
    images: List[ImageSpec] = Field(default_factory=list)
    dedup_key: Optional[str] = None
    deck: Optional[constr(strip_whitespace=True, min_length=1)] = Field(
        default=None, alias="deckName"
    )
    model: Optional[constr(strip_whitespace=True, min_length=1)] = Field(
        default=None, alias="modelName"
    )

    if ConfigDict is not None:  # pragma: no branch - для Pydantic v2
        model_config = ConfigDict(populate_by_name=True)
    else:  # pragma: no cover - используется в Pydantic v1
        class Config:
            allow_population_by_field_name = True

    if model_validator is not None:  # pragma: no branch - зависит от версии Pydantic

        @model_validator(mode="before")  # type: ignore[misc]
        @classmethod
        def _ensure_fields(cls, values):
            return _coerce_note_fields(cls, values)

    elif root_validator is not None:  # pragma: no cover - fallback для Pydantic v1

        @root_validator(pre=True)
        def _ensure_fields(cls, values):  # type: ignore[override]
            return _coerce_note_fields(cls, values)

    if field_validator is not None:  # pragma: no branch - зависит от версии Pydantic

        @field_validator("tags", mode="before")  # type: ignore[misc]
        @classmethod
        def _normalize_tags(cls, value):
            return _normalize_note_input_tags(value)

    elif validator is not None:  # pragma: no cover - для Pydantic v1

        @validator("tags", pre=True)  # type: ignore[misc]
        def _normalize_tags(cls, value):  # type: ignore[override]
            return _normalize_note_input_tags(value)


def _default_deck() -> str:
    return config.DEFAULT_DECK


def _default_model() -> str:
    return config.DEFAULT_MODEL


class AddNotesArgs(BaseModel):
    deck: constr(strip_whitespace=True, min_length=1) = Field(default_factory=_default_deck)
    model: constr(strip_whitespace=True, min_length=1) = Field(
        default_factory=_default_model
    )
    notes: List[NoteInput] = Field(min_length=1)


class AddNotesResult(BaseModel):
    added: int
    skipped: int
    details: List[dict] = Field(default_factory=list)


class NoteUpdate(BaseModel):
    note_id: int = Field(alias="noteId")
    fields: Optional[Dict[str, Any]] = None
    add_tags: List[str] = Field(default_factory=list, alias="addTags")
    remove_tags: List[str] = Field(default_factory=list, alias="removeTags")
    deck: Optional[constr(strip_whitespace=True, min_length=1)] = Field(
        default=None, alias="deckName"
    )
    images: List[ImageSpec] = Field(default_factory=list, alias="attachments")

    if ConfigDict is not None:  # pragma: no branch
        model_config = ConfigDict(populate_by_name=True)
    else:  # pragma: no cover
        class Config:
            allow_population_by_field_name = True

    if field_validator is not None:  # pragma: no branch

        @field_validator("add_tags", mode="before")  # type: ignore[misc]
        @classmethod
        def _normalize_add_tags(cls, value):
            return _normalize_note_input_tags(value)

        @field_validator("remove_tags", mode="before")  # type: ignore[misc]
        @classmethod
        def _normalize_remove_tags(cls, value):
            return _normalize_note_input_tags(value)

    elif validator is not None:  # pragma: no cover

        @validator("add_tags", "remove_tags", pre=True)  # type: ignore[misc]
        def _normalize_tags(cls, value):  # type: ignore[override]
            return _normalize_note_input_tags(value)


class UpdateNotesArgs(BaseModel):
    notes: List[NoteUpdate] = Field(min_length=1)


class UpdateNotesResult(BaseModel):
    updated: int
    skipped: int
    details: List[dict] = Field(default_factory=list)


class NoteInfoArgs(BaseModel):
    note_ids: List[int] = Field(min_length=1, alias="noteIds")

    if ConfigDict is not None:  # pragma: no branch
        model_config = ConfigDict(populate_by_name=True)
    else:  # pragma: no cover
        class Config:
            allow_population_by_field_name = True


class FindNotesArgs(BaseModel):
    query: constr(strip_whitespace=True, min_length=1)
    limit: Optional[int] = Field(default=None, ge=1)
    offset: Optional[int] = Field(default=0, ge=0)


class NoteInfo(BaseModel):
    note_id: int = Field(alias="noteId")
    model_name: Optional[str] = Field(default=None, alias="modelName")
    deck_name: Optional[str] = Field(default=None, alias="deckName")
    tags: List[str] = Field(default_factory=list)
    fields: Dict[str, str] = Field(default_factory=dict)
    cards: List[int] = Field(default_factory=list)

    if ConfigDict is not None:  # pragma: no branch
        model_config = ConfigDict(populate_by_name=True)
    else:  # pragma: no cover
        class Config:
            allow_population_by_field_name = True


class NoteInfoResponse(BaseModel):
    notes: List[Optional[NoteInfo]] = Field(default_factory=list)


class FindNotesResponse(BaseModel):
    note_ids: List[int] = Field(default_factory=list, alias="noteIds")
    notes: List[Optional[NoteInfo]] = Field(default_factory=list)

    if ConfigDict is not None:  # pragma: no branch
        model_config = ConfigDict(populate_by_name=True)
    else:  # pragma: no cover
        class Config:
            allow_population_by_field_name = True


class ModelInfo(BaseModel):
    model: str
    fields: List[str]
    templates: Dict[str, Dict[str, str]]
    styling: str


__all__ = [
    "AddNotesArgs",
    "AddNotesResult",
    "FindNotesArgs",
    "FindNotesResponse",
    "ModelInfo",
    "NOTE_RESERVED_TOP_LEVEL_KEYS",
    "NoteInfo",
    "NoteInfoArgs",
    "NoteInfoResponse",
    "NoteInput",
]
