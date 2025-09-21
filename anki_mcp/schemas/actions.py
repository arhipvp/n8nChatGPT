"""Общие Pydantic-модели для прямых вызовов AnkiConnect."""

from __future__ import annotations

from typing import Any, Dict, Optional

from ..compat import BaseModel, ConfigDict, constr, field_validator, validator


class InvokeActionArgs(BaseModel):
    """Аргументы инструмента универсального вызова AnkiConnect."""

    action: constr(strip_whitespace=True, min_length=1)
    params: Optional[Dict[str, Any]] = None
    version: Optional[int] = None

    if ConfigDict is not None:  # pragma: no branch - поддержка Pydantic v2
        model_config = ConfigDict(extra="allow")
    else:  # pragma: no cover - конфигурация для Pydantic v1
        class Config:
            extra = "allow"

    if field_validator is not None:  # pragma: no branch - Pydantic v2

        @field_validator("version", mode="before")  # type: ignore[misc]
        @classmethod
        def _validate_version(cls, value: Any) -> Any:
            if isinstance(value, bool):
                raise TypeError("version must be an integer")
            return value

    elif validator is not None:  # pragma: no cover - Pydantic v1

        @validator("version", pre=True)  # type: ignore[misc]
        def _validate_version(cls, value: Any) -> Any:
            if isinstance(value, bool):
                raise TypeError("version must be an integer")
            return value


__all__ = ["InvokeActionArgs"]
