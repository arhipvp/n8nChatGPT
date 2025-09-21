"""Пакет с MCP-инструментами."""

from .anki import (
    add_from_model,
    add_notes,
    create_model,
    delete_decks,
    delete_notes,
    find_notes,
    invoke_action,
    list_decks,
    model_info,
    note_info,
    rename_deck,
    update_notes,
)
from .misc import greet


__all__ = [
    "add_from_model",
    "add_notes",
    "create_model",
    "delete_decks",
    "delete_notes",
    "find_notes",
    "greet",
    "invoke_action",
    "list_decks",
    "model_info",
    "note_info",
    "rename_deck",
    "update_notes",
]
