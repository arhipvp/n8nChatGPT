"""Pydantic-схемы для работы с моделями Anki."""

from __future__ import annotations

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
)


def _normalize_case_insensitive(values: Mapping[str, Any]) -> Dict[str, Any]:
    normalized: Dict[str, Any] = dict(values)
    lower_map = {key.lower(): key for key in values.keys()}
    for target, aliases in (
        ("name", ["Name"]),
        ("front", ["Front"]),
        ("back", ["Back"]),
        ("model_name", ["model", "modelName"]),
        ("in_order_fields", ["fields", "inOrderFields"]),
        ("card_templates", ["cardTemplates", "templates"]),
        ("css", ["style", "css"]),
        ("is_cloze", ["isCloze", "cloze"]),
        ("options", ["options"]),
    ):
        if target in normalized:
            continue
        for alias in aliases:
            lookup = lower_map.get(alias.lower())
            if lookup and lookup in values:
                normalized[target] = values[lookup]
                break
    return normalized


class CardTemplateSpec(BaseModel):
    """Структура шаблона карточки модели Anki."""

    name: constr(strip_whitespace=True, min_length=1)
    front: str
    back: str

    if ConfigDict is not None:  # pragma: no branch - совместимость с Pydantic v2
        model_config = ConfigDict(populate_by_name=True)
    else:  # pragma: no cover - конфигурация для Pydantic v1
        class Config:
            allow_population_by_field_name = True

    if model_validator is not None:  # pragma: no branch

        @model_validator(mode="before")
        @classmethod
        def _normalize_input(cls, values: Any) -> Any:
            if isinstance(values, Mapping):
                return _normalize_case_insensitive(values)
            return values

    elif root_validator is not None:  # pragma: no cover - Pydantic v1

        @root_validator(pre=True)
        def _normalize_input(cls, values: Any) -> Any:  # type: ignore[override]
            if isinstance(values, Mapping):
                return _normalize_case_insensitive(values)
            return values

    @field_validator("front", "back", mode="before")  # type: ignore[misc]
    @classmethod
    def _ensure_string(cls, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        return str(value)


class CreateModelArgs(BaseModel):
    """Аргументы инструмента создания модели Anki."""

    model_name: constr(strip_whitespace=True, min_length=1)
    in_order_fields: List[constr(strip_whitespace=True, min_length=1)] = Field(
        min_length=1
    )
    card_templates: List[CardTemplateSpec] = Field(min_length=1)
    css: str = ""
    is_cloze: Optional[bool] = None
    options: Dict[str, Any] = Field(default_factory=dict)

    if ConfigDict is not None:  # pragma: no branch
        model_config = ConfigDict(populate_by_name=True)
    else:  # pragma: no cover - Pydantic v1
        class Config:
            allow_population_by_field_name = True

    if model_validator is not None:  # pragma: no branch

        @model_validator(mode="before")
        @classmethod
        def _normalize_input(cls, values: Any) -> Any:
            if isinstance(values, Mapping):
                normalized = _normalize_case_insensitive(values)
                return normalized
            return values

    elif root_validator is not None:  # pragma: no cover - Pydantic v1

        @root_validator(pre=True)
        def _normalize_input(cls, values: Any) -> Any:  # type: ignore[override]
            if isinstance(values, Mapping):
                return _normalize_case_insensitive(values)
            return values

    @field_validator("in_order_fields", mode="before")  # type: ignore[misc]
    @classmethod
    def _ensure_list(cls, value: Any) -> List[Any]:
        if isinstance(value, str):
            return [value]
        if isinstance(value, Iterable):
            return list(value)
        raise TypeError("in_order_fields must be a list of strings")

    @field_validator("css", mode="before")  # type: ignore[misc]
    @classmethod
    def _ensure_css(cls, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        return str(value)

    @field_validator("options", mode="before")  # type: ignore[misc]
    @classmethod
    def _ensure_options(cls, value: Any) -> Dict[str, Any]:
        if value is None:
            return {}
        if isinstance(value, Mapping):
            return dict(value)
        raise TypeError("options must be a mapping of extra parameters")


class CreateModelResult(BaseModel):
    """Результат вызова инструмента создания модели."""

    model_name: constr(strip_whitespace=True, min_length=1)
    in_order_fields: List[constr(strip_whitespace=True, min_length=1)]
    card_templates: List[CardTemplateSpec]
    css: str = ""
    options: Dict[str, Any] = Field(default_factory=dict)
    anki_response: Any = None

    if ConfigDict is not None:  # pragma: no branch
        model_config = ConfigDict(populate_by_name=True)
    else:  # pragma: no cover - Pydantic v1
        class Config:
            allow_population_by_field_name = True

    if model_validator is not None:  # pragma: no branch

        @model_validator(mode="before")
        @classmethod
        def _normalize_input(cls, values: Any) -> Any:
            if isinstance(values, Mapping):
                normalized = _normalize_case_insensitive(values)
                return normalized
            return values

    elif root_validator is not None:  # pragma: no cover - Pydantic v1

        @root_validator(pre=True)
        def _normalize_input(cls, values: Any) -> Any:  # type: ignore[override]
            if isinstance(values, Mapping):
                return _normalize_case_insensitive(values)
            return values

    @field_validator("css", mode="before")  # type: ignore[misc]
    @classmethod
    def _ensure_css(cls, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        return str(value)

    @field_validator("options", mode="before")  # type: ignore[misc]
    @classmethod
    def _ensure_options(cls, value: Any) -> Dict[str, Any]:
        if value is None:
            return {}
        if isinstance(value, Mapping):
            return dict(value)
        raise TypeError("options must be a mapping of extra parameters")
