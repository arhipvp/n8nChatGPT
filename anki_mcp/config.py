"""Конфигурация и загрузка окружения MCP-сервера."""

from __future__ import annotations

import os
from typing import Optional


def _env_default(name: str, fallback: str) -> str:
    value = os.environ.get(name)
    if value is None:
        return fallback
    trimmed = value.strip()
    return trimmed or fallback


def _env_optional(name: str) -> Optional[str]:
    value = os.environ.get(name)
    if value is None:
        return None
    trimmed = value.strip()
    return trimmed or None


def reload_from_env() -> None:
    global DEFAULT_DECK, DEFAULT_MODEL, SEARCH_API_URL, SEARCH_API_KEY, ANKI_URL, ENVIRONMENT_INFO

    DEFAULT_DECK = _env_default("ANKI_DEFAULT_DECK", "Default")
    DEFAULT_MODEL = _env_default("ANKI_DEFAULT_MODEL", "Поля для ChatGPT")
    SEARCH_API_URL = _env_optional("SEARCH_API_URL")
    SEARCH_API_KEY = _env_optional("SEARCH_API_KEY")
    ANKI_URL = _env_default("ANKI_URL", "http://127.0.0.1:8765")
    ENVIRONMENT_INFO = {"defaultDeck": DEFAULT_DECK, "defaultModel": DEFAULT_MODEL}


reload_from_env()


__all__ = [
    "ANKI_URL",
    "DEFAULT_DECK",
    "DEFAULT_MODEL",
    "ENVIRONMENT_INFO",
    "SEARCH_API_KEY",
    "SEARCH_API_URL",
    "reload_from_env",
    "_env_default",
    "_env_optional",
]
