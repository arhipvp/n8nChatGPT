"""Клиентские вызовы к AnkiConnect."""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional

import httpx

from .. import config


async def anki_call(
    action: str,
    params: Optional[Mapping[str, Any]] = None,
    *,
    version: int = 6,
):
    """Выполнить RPC-вызов AnkiConnect.

    Проводит базовую валидацию аргументов и проксирует запрос к серверу.
    """

    if not isinstance(action, str):
        raise TypeError("action must be a string")
    trimmed_action = action.strip()
    if not trimmed_action:
        raise ValueError("action must be a non-empty string")

    if params is None:
        normalized_params: Dict[str, Any] = {}
    elif isinstance(params, dict):
        normalized_params = dict(params)
    elif isinstance(params, Mapping):
        normalized_params = dict(params)
    else:  # pragma: no cover - защитный хэндлинг типов
        raise TypeError("params must be a mapping of argument names to values")

    if isinstance(version, bool) or not isinstance(version, int):
        raise TypeError("version must be an integer")

    payload = {
        "action": trimmed_action,
        "version": version,
        "params": normalized_params,
    }
    async with httpx.AsyncClient(timeout=25) as client:
        response = await client.post(config.ANKI_URL, json=payload)
        response.raise_for_status()
        data = response.json()
        if data.get("error"):
            raise RuntimeError(f"Anki error: {data['error']}")
        return data["result"]


async def store_media_file(filename: str, data_b64: str):
    """Сохранить файл мультимедиа через AnkiConnect."""

    return await anki_call("storeMediaFile", {"filename": filename, "data": data_b64})


__all__ = ["anki_call", "store_media_file", "httpx"]
