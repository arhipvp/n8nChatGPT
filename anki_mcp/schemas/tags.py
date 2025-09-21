"""Pydantic-схемы для работы с тегами Anki."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping

from ..compat import BaseModel, Field, field_validator, validator


def _normalize_tags(raw_tags: Any) -> List[str]:
    """Преобразует произвольную коллекцию тегов в отсортированный список."""

    if raw_tags is None:
        return []

    if isinstance(raw_tags, (str, bytes)):
        raise TypeError("tags must be provided as a sequence of strings")

    if isinstance(raw_tags, Mapping):
        raise TypeError("tags must be provided as a sequence of strings")

    if not isinstance(raw_tags, Iterable):
        raise TypeError("tags must be provided as a sequence of strings")

    normalized: List[str] = []
    for index, tag in enumerate(raw_tags):
        if not isinstance(tag, str):
            raise ValueError(
                f"tags must contain only strings, got {tag!r} at index {index}"
            )

        stripped = tag.strip()
        if not stripped:
            raise ValueError(f"tags must not contain empty values (index {index})")

        normalized.append(stripped)

    unique: Dict[str, str] = {}
    for name in normalized:
        key = name.casefold()
        unique.setdefault(key, name)

    unique_sorted = sorted(unique.values(), key=lambda name: (name.casefold(), name))
    return unique_sorted


class ListTagsResponse(BaseModel):
    """Ответ AnkiConnect `getTags`."""

    tags: List[str] = Field(default_factory=list)

    if field_validator is not None:  # pragma: no branch - зависит от версии Pydantic

        @field_validator("tags", mode="before")  # type: ignore[misc]
        @classmethod
        def _normalize_tags_field(cls, value):
            return _normalize_tags(value)

    elif validator is not None:  # pragma: no cover - fallback для Pydantic v1

        @validator("tags", pre=True)  # type: ignore[misc]
        def _normalize_tags_field(cls, value):  # type: ignore[override]
            return _normalize_tags(value)


TagsList = ListTagsResponse


__all__ = ["ListTagsResponse", "TagsList"]

