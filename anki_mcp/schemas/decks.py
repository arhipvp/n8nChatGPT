"""Pydantic-схемы для управления колодами Anki."""

from __future__ import annotations

from typing import List, Optional

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


class DeckNewOptions(BaseModel):
    """Настройки для новых карточек (раздел `new`)."""

    per_day: int = Field(alias="perDay")
    delays: List[float] = Field(default_factory=list)
    ints: List[int] = Field(default_factory=list)
    initial_factor: int = Field(alias="initialFactor")
    order: int
    bury: bool = Field(default=False)
    separate: Optional[bool] = None

    if ConfigDict is not None:  # pragma: no branch - зависит от версии Pydantic
        model_config = ConfigDict(populate_by_name=True, extra="allow")
    else:  # pragma: no cover - fallback для Pydantic v1

        class Config:
            allow_population_by_field_name = True
            extra = "allow"


class DeckRevOptions(BaseModel):
    """Настройки для повторений (раздел `rev`)."""

    per_day: int = Field(alias="perDay")
    ease4: float
    hard_factor: float = Field(alias="hardFactor")
    interval_factor: float = Field(alias="ivlFct")
    max_interval: int = Field(alias="maxIvl")
    min_space: int = Field(alias="minSpace")
    bury: bool = Field(default=False)
    seed: Optional[int] = None

    if ConfigDict is not None:  # pragma: no branch - зависит от версии Pydantic
        model_config = ConfigDict(populate_by_name=True, extra="allow")
    else:  # pragma: no cover - fallback для Pydantic v1

        class Config:
            allow_population_by_field_name = True
            extra = "allow"


class DeckLapseOptions(BaseModel):
    """Настройки для повторения пропущенных карточек (раздел `lapse`)."""

    delays: List[float] = Field(default_factory=list)
    leech_action: int = Field(alias="leechAction")
    leech_fails: int = Field(alias="leechFails")
    min_interval: int = Field(alias="minInt")
    multiplier: float = Field(alias="mult")

    if ConfigDict is not None:  # pragma: no branch - зависит от версии Pydantic
        model_config = ConfigDict(populate_by_name=True, extra="allow")
    else:  # pragma: no cover - fallback для Pydantic v1

        class Config:
            allow_population_by_field_name = True
            extra = "allow"


class DeckConfig(BaseModel):
    """Полный набор настроек колоды Anki."""

    id: Optional[int] = None
    name: constr(strip_whitespace=True, min_length=1)
    autoplay: Optional[bool] = None
    dyn: Optional[int] = None
    lapse: DeckLapseOptions
    max_taken: Optional[int] = Field(default=None, alias="maxTaken")
    mod: Optional[int] = None
    new: DeckNewOptions
    replayq: Optional[bool] = None
    rev: DeckRevOptions
    timer: Optional[int] = None
    usn: Optional[int] = None

    if ConfigDict is not None:  # pragma: no branch - зависит от версии Pydantic
        model_config = ConfigDict(populate_by_name=True, extra="allow")
    else:  # pragma: no cover - fallback для Pydantic v1

        class Config:
            allow_population_by_field_name = True
            extra = "allow"


class GetDeckConfigArgs(BaseModel):
    """Аргументы метода `getDeckConfig`."""

    deck: constr(strip_whitespace=True, min_length=1)


class SaveDeckConfigArgs(BaseModel):
    """Аргументы инструмента сохранения настроек колоды."""

    config: DeckConfig
    deck: Optional[constr(strip_whitespace=True, min_length=1)] = None

