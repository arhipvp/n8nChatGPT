"""Pydantic-схемы для управления колодами Anki."""

from __future__ import annotations

from typing import List

from ..compat import BaseModel, ConfigDict, Field, constr


class DeckInfo(BaseModel):
    """Краткая информация о колоде."""

    id: int
    name: constr(strip_whitespace=True, min_length=1)


class ListDecksResponse(BaseModel):
    """Ответ AnkiConnect `deckNamesAndIds`."""

    decks: List[DeckInfo] = Field(default_factory=list)


class CreateDeckArgs(BaseModel):
    """Аргументы метода `createDeck`."""

    deck: constr(strip_whitespace=True, min_length=1) = Field(alias="name")

    if ConfigDict is not None:  # pragma: no branch - зависит от версии Pydantic
        model_config = ConfigDict(populate_by_name=True)
    else:  # pragma: no cover - fallback для Pydantic v1

        class Config:
            allow_population_by_field_name = True


class RenameDeckArgs(BaseModel):
    """Аргументы метода `renameDeck`."""

    old_name: constr(strip_whitespace=True, min_length=1) = Field(alias="oldName")
    new_name: constr(strip_whitespace=True, min_length=1) = Field(alias="newName")

    if ConfigDict is not None:  # pragma: no branch - зависит от версии Pydantic
        model_config = ConfigDict(populate_by_name=True)
    else:  # pragma: no cover - fallback для Pydantic v1

        class Config:
            allow_population_by_field_name = True


class DeleteDecksArgs(BaseModel):
    """Аргументы метода `deleteDecks`."""

    decks: List[constr(strip_whitespace=True, min_length=1)] = Field(min_length=1)
    cards_too: bool = Field(default=False, alias="cardsToo")

    if ConfigDict is not None:  # pragma: no branch - зависит от версии Pydantic
        model_config = ConfigDict(populate_by_name=True)
    else:  # pragma: no cover - fallback для Pydantic v1

        class Config:
            allow_population_by_field_name = True
