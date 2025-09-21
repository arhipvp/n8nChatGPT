"""Схемы для действий поиска."""

from __future__ import annotations

from typing import List, Optional

from ..compat import AnyHttpUrl, BaseModel, ConfigDict, Field, constr


class SearchRequest(BaseModel):
    query: constr(strip_whitespace=True, min_length=1)
    limit: Optional[int] = Field(default=None, ge=1)
    cursor: Optional[constr(strip_whitespace=True, min_length=1)] = None

    if ConfigDict is not None:  # pragma: no branch
        model_config = ConfigDict(populate_by_name=True)
    else:  # pragma: no cover
        class Config:
            allow_population_by_field_name = True


class SearchResult(BaseModel):
    title: Optional[str] = None
    url: Optional[AnyHttpUrl] = None
    snippet: Optional[str] = None
    content: Optional[str] = None
    score: Optional[float] = None

    if ConfigDict is not None:  # pragma: no branch
        model_config = ConfigDict(extra="allow")
    else:  # pragma: no cover
        class Config:
            extra = "allow"


class SearchResponse(BaseModel):
    results: List[SearchResult] = Field(default_factory=list)
    next_cursor: Optional[str] = Field(default=None, alias="nextCursor")

    if ConfigDict is not None:  # pragma: no branch
        model_config = ConfigDict(populate_by_name=True)
    else:  # pragma: no cover
        class Config:
            allow_population_by_field_name = True


__all__ = ["SearchRequest", "SearchResponse", "SearchResult"]
