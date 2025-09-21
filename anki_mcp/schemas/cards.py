"""Pydantic-схемы для карточек Anki."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Dict, List, Mapping, Optional, Tuple

from ..compat import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
    root_validator,
    validator,
)

_KNOWN_CARD_KEYS = {
    "cardId",
    "card_id",
    "noteId",
    "note_id",
    "deckName",
    "deck_name",
    "modelName",
    "model_name",
    "template",
    "ordinal",
    "ord",
    "queue",
    "type",
    "due",
    "dueString",
    "due_string",
    "interval",
    "intervalString",
    "interval_string",
    "factor",
    "reps",
    "lapses",
    "left",
    "mod",
    "question",
    "answer",
    "extra",
}


def _normalize_card_ids(value: Any) -> List[int]:
    if value is None:
        return []

    if isinstance(value, Mapping):
        candidates = value.values()
    else:
        candidates = value

    if isinstance(candidates, (str, bytes)):
        raise TypeError("cardIds must be a sequence of integers")

    if not isinstance(candidates, Iterable):
        raise TypeError("cardIds must be a sequence of integers")

    normalized: List[int] = []
    for index, raw_id in enumerate(candidates):
        if isinstance(raw_id, bool):
            raise ValueError(
                f"cardIds must contain integers, got boolean at index {index}"
            )
        try:
            normalized.append(int(raw_id))
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"cardIds must contain integers, got {raw_id!r} at index {index}"
            ) from exc

    return normalized


def _normalize_cards_to_notes(value: Any) -> Dict[int, int]:
    if value is None:
        return {}

    if isinstance(value, Mapping):
        items: Iterable[Tuple[Any, Any]] = value.items()
    else:
        if isinstance(value, (str, bytes)):
            raise TypeError("cards_to_notes must be a mapping or iterable of pairs")

        if not isinstance(value, Iterable):
            raise TypeError("cards_to_notes must be a mapping or iterable of pairs")

        items = []  # type: ignore[assignment]
        for index, entry in enumerate(value):
            if isinstance(entry, Mapping):
                if len(entry) != 1:
                    raise ValueError(
                        "cards_to_notes entries as mappings must contain exactly one item"
                    )
                entry_items = list(entry.items())
                items.append(entry_items[0])
            else:
                try:
                    card_id_raw, note_id_raw = entry  # type: ignore[misc]
                except Exception as exc:
                    raise ValueError(
                        "cards_to_notes iterable entries must be pairs"
                    ) from exc
                items.append((card_id_raw, note_id_raw))

    normalized: Dict[int, int] = {}
    for index, (card_raw, note_raw) in enumerate(items):
        if isinstance(card_raw, bool):
            raise ValueError(
                f"cards_to_notes keys must be integers, got boolean at index {index}"
            )
        if isinstance(note_raw, bool):
            raise ValueError(
                f"cards_to_notes values must be integers, got boolean at index {index}"
            )
        try:
            card_id = int(card_raw)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"cards_to_notes keys must be integers, got {card_raw!r} at index {index}"
            ) from exc
        try:
            note_id = int(note_raw)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"cards_to_notes values must be integers, got {note_raw!r} at index {index}"
            ) from exc
        normalized[card_id] = note_id

    return normalized


class CardIdsArgs(BaseModel):
    """Базовая схема аргументов, содержащая список идентификаторов карточек."""

    card_ids: List[int] = Field(alias="cardIds", min_length=1)

    if ConfigDict is not None:  # pragma: no branch - поддержка Pydantic v2
        model_config = ConfigDict(populate_by_name=True)
    else:  # pragma: no cover - fallback для Pydantic v1
        class Config:
            allow_population_by_field_name = True

    if field_validator is not None:  # pragma: no branch - зависит от версии Pydantic

        @field_validator("card_ids", mode="before")  # type: ignore[misc]
        @classmethod
        def _normalize_ids(cls, value: Any) -> List[int]:
            return _normalize_card_ids(value)

    elif validator is not None:  # pragma: no cover - Pydantic v1 fallback

        @validator("card_ids", pre=True)  # type: ignore[misc]
        def _normalize_ids(cls, value: Any):  # type: ignore[override]
            return list(_normalize_card_ids(value))


class CardsInfoArgs(CardIdsArgs):
    """Аргументы для инструмента `cardsInfo`."""


class CardsToNotesArgs(CardIdsArgs):
    """Аргументы для инструмента `cardsToNotes`."""


class CardInfo(BaseModel):
    card_id: int = Field(alias="cardId")
    note_id: int = Field(alias="noteId")
    deck_name: str = Field(alias="deckName")
    model_name: Optional[str] = Field(default=None, alias="modelName")
    template: Optional[str] = None
    ordinal: Optional[int] = Field(default=None, alias="ord")
    queue: Optional[int] = None
    type: Optional[int] = None
    due: Optional[int] = None
    due_string: Optional[str] = Field(default=None, alias="dueString")
    interval: Optional[int] = None
    interval_string: Optional[str] = Field(default=None, alias="intervalString")
    factor: Optional[int] = None
    reps: Optional[int] = None
    lapses: Optional[int] = None
    left: Optional[int] = None
    mod: Optional[int] = None
    question: Optional[str] = None
    answer: Optional[str] = None
    extra: Dict[str, Any] = Field(default_factory=dict)

    if ConfigDict is not None:  # pragma: no branch - поддержка Pydantic v2
        model_config = ConfigDict(populate_by_name=True)
    else:  # pragma: no cover - fallback для Pydantic v1
        class Config:
            allow_population_by_field_name = True
            extra = "allow"

    if model_validator is not None:  # pragma: no branch - Pydantic v2

        @model_validator(mode="before")  # type: ignore[misc]
        @classmethod
        def _populate_extra(cls, values: Any):
            if not isinstance(values, Mapping):
                return values

            normalized = dict(values)
            extra = dict(normalized.get("extra") or {})
            for key in list(normalized.keys()):
                if key in _KNOWN_CARD_KEYS:
                    continue
                extra[key] = normalized.pop(key)
            normalized["extra"] = extra
            return normalized

    elif root_validator is not None:  # pragma: no cover - Pydantic v1 fallback

        @root_validator(pre=True)
        def _populate_extra(cls, values):  # type: ignore[override]
            if not isinstance(values, Mapping):
                return values
            normalized = dict(values)
            extra = dict(normalized.get("extra") or {})
            for key in list(normalized.keys()):
                if key in _KNOWN_CARD_KEYS:
                    continue
                extra[key] = normalized.pop(key)
            normalized["extra"] = extra
            return normalized


class CardsToNotesResponse(BaseModel):
    cards_to_notes: Dict[int, int] = Field(default_factory=dict, alias="cardsToNotes")

    if ConfigDict is not None:  # pragma: no branch - поддержка Pydantic v2
        model_config = ConfigDict(populate_by_name=True)
    else:  # pragma: no cover - fallback для Pydantic v1
        class Config:
            allow_population_by_field_name = True

    if field_validator is not None:  # pragma: no branch - зависит от версии Pydantic

        @field_validator("cards_to_notes", mode="before")  # type: ignore[misc]
        @classmethod
        def _normalize_mapping(cls, value: Any) -> Dict[int, int]:
            return _normalize_cards_to_notes(value)

    elif validator is not None:  # pragma: no cover - Pydantic v1 fallback

        @validator("cards_to_notes", pre=True)  # type: ignore[misc]
        def _normalize_mapping(cls, value):  # type: ignore[override]
            return dict(_normalize_cards_to_notes(value))


__all__ = [
    "CardIdsArgs",
    "CardInfo",
    "CardsInfoArgs",
    "CardsToNotesArgs",
    "CardsToNotesResponse",
]
