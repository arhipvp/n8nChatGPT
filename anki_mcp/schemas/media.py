"""Pydantic-схемы для работы с медиафайлами Anki."""

from __future__ import annotations

from typing import Optional

from ..compat import BaseModel, ConfigDict, Field, constr


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
