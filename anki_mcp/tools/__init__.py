"""Пакет с MCP-инструментами."""

from .anki import add_from_model, add_notes, find_notes, model_info, note_info
from .misc import greet


__all__ = [
    "add_from_model",
    "add_notes",
    "find_notes",
    "greet",
    "model_info",
    "note_info",
]
