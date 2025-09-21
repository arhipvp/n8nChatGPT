"""Пакет с MCP-инструментами."""

from .anki import (
    add_from_model,
    add_notes,
    create_model,
    delete_decks,
    delete_media,
    delete_notes,
    find_notes,
    get_media,
    invoke_action,
    list_decks,
    model_info,
    note_info,
    rename_deck,
    update_model_templates,
    update_notes,
)
from .misc import greet


__all__ = [
    "add_from_model",
    "add_notes",
    "create_model",
    "delete_decks",
    "delete_media",
    "delete_notes",
    "find_notes",
    "greet",
    "get_media",
    "invoke_action",
    "list_decks",
    "model_info",
    "note_info",
    "rename_deck",
    "update_model_templates",
    "update_notes",
]
