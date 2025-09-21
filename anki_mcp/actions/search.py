"""Определение MCP-действий."""

from __future__ import annotations

from .. import app, config
from ..schemas import SearchRequest, SearchResponse
from ..services.search import perform_search


@app.action(name="search")
async def search(request: SearchRequest) -> SearchResponse:
    if not config.SEARCH_API_URL:
        raise RuntimeError("SEARCH_API_URL is not configured")

    return await perform_search(request, config.SEARCH_API_URL, config.SEARCH_API_KEY)


__all__ = ["search"]
