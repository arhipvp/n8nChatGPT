"""Сервисы для работы с внешним поиском."""

from __future__ import annotations

from typing import Any, Dict, Optional

import httpx

from ..compat import model_validate
from ..schemas import SearchRequest, SearchResponse


def _normalize_search_payload(raw_payload: Any) -> dict:
    if not isinstance(raw_payload, dict):
        raise ValueError("Search API response must be a JSON object")

    payload = dict(raw_payload)
    results = payload.get("results")
    if results is None and "items" in payload:
        results = payload["items"]

    if results is None:
        raise ValueError("Search API response is missing 'results'")
    if not isinstance(results, list):
        raise ValueError("Search API 'results' must be a list")

    next_cursor = payload.get("nextCursor")
    if next_cursor is None:
        next_cursor = payload.get("next_cursor")
    if next_cursor is None:
        next_cursor = payload.get("nextPageToken") or payload.get("next_page_token")

    normalized: Dict[str, Any] = {"results": results}
    if next_cursor is not None:
        normalized["nextCursor"] = next_cursor
    return normalized


async def perform_search(
    request: SearchRequest,
    base_url: str,
    api_key: Optional[str],
) -> SearchResponse:
    payload: Dict[str, Any] = {"query": request.query}
    if request.limit is not None:
        payload["limit"] = request.limit
    if request.cursor is not None:
        payload["cursor"] = request.cursor

    headers: Dict[str, str] = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(base_url, json=payload, headers=headers or None)

    response.raise_for_status()
    normalized_payload = _normalize_search_payload(response.json())
    return model_validate(SearchResponse, normalized_payload)


__all__ = ["httpx", "perform_search", "_normalize_search_payload"]
