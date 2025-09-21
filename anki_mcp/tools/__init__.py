"""Пакет с MCP-инструментами."""

from .anki import (
    add_from_model,
    add_notes,
    create_model,
    find_notes,
    model_info,
    note_info,
    update_notes,
)
from .misc import greet


__all__ = [
    "add_from_model",
    "add_notes",
    "create_model",
    "find_notes",
    "greet",
    "model_info",
    "note_info",
    "update_notes",
]
