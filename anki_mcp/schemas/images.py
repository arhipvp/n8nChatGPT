"""Схемы, связанные с изображениями."""

from __future__ import annotations

from typing import Optional

from ..compat import AnyHttpUrl, BaseModel, ConfigDict, Field, constr


class ImageSpec(BaseModel):
    image_base64: Optional[str] = None
    image_url: Optional[AnyHttpUrl] = Field(default=None, alias="url")
    target_field: constr(strip_whitespace=True, min_length=1) = "Back"
    filename: Optional[str] = None
    max_side: int = Field(default=768, ge=1)

    if ConfigDict is not None:  # pragma: no branch - атрибут есть только в Pydantic v2
        model_config = ConfigDict(populate_by_name=True)
    else:  # pragma: no cover - используется только в Pydantic v1
        class Config:
            allow_population_by_field_name = True


__all__ = ["ImageSpec"]
