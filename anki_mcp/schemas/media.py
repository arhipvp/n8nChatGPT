"""Pydantic-схемы для работы с медиафайлами Anki."""

from __future__ import annotations

from typing import Any, Mapping, Optional

from ..compat import (
    BaseModel,
    ConfigDict,
    Field,
    constr,
    model_validator,
    root_validator,
)


class MediaRequest(BaseModel):
    """Запрос на получение или удаление медиафайла."""

    filename: constr(strip_whitespace=True, min_length=1)


class MediaResponse(BaseModel):
    """Ответ на запрос медиафайла."""

    filename: str
    data_base64: str = Field(alias="dataBase64")
    size_bytes: Optional[int] = Field(default=None, alias="sizeBytes")

    if ConfigDict is not None:  # pragma: no branch - зависит от версии Pydantic
        model_config = ConfigDict(populate_by_name=True)
    else:  # pragma: no cover - используется в Pydantic v1

        class Config:
            allow_population_by_field_name = True


class DeleteMediaArgs(BaseModel):
    """Аргументы для удаления медиафайла."""

    filename: constr(strip_whitespace=True, min_length=1)


class StoreMediaArgs(BaseModel):
    """Аргументы для сохранения медиафайла в коллекции Anki."""

    filename: constr(strip_whitespace=True, min_length=1)
    data_base64: constr(min_length=1) = Field(alias="dataBase64")

    if ConfigDict is not None:  # pragma: no branch - зависит от версии Pydantic
        model_config = ConfigDict(populate_by_name=True)
    else:  # pragma: no cover - используется в Pydantic v1

        class Config:
            allow_population_by_field_name = True
            allow_population_by_alias = True

    if model_validator is not None:  # pragma: no branch - доступно в Pydantic v2

        @model_validator(mode="before")
        @classmethod
        def _support_alt_aliases(cls, values: Any) -> Any:
            if isinstance(values, Mapping):
                if "data_base64" not in values:
                    if "data" in values:
                        values = dict(values)
                        values.setdefault("data_base64", values.pop("data"))
                    elif "dataBase64" in values:
                        values = dict(values)
                        values.setdefault("data_base64", values.pop("dataBase64"))
            return values

    elif root_validator is not None:  # pragma: no cover - Pydantic v1 fallback

        @root_validator(pre=True)
        def _support_alt_aliases(cls, values: Any):
            if isinstance(values, Mapping) and "data_base64" not in values:
                if "data" in values:
                    values = dict(values)
                    values.setdefault("data_base64", values.pop("data"))
                elif "dataBase64" in values:
                    values = dict(values)
                    values.setdefault("data_base64", values.pop("dataBase64"))
            return values
