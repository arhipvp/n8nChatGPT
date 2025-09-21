"""Пакет с MCP-инструментами."""

from .decks import (
    create_deck,
    delete_decks,
    get_deck_config,
    list_decks,
    list_tags,
    rename_deck,
    save_deck_config,
)
from .media import delete_media, get_media, store_media
from .models import (
    create_model,
    list_models,
    model_info,
    update_model_styling,
    update_model_templates,
)
from .notes import (
    add_from_model,
    add_notes,
    cards_info,
    cards_to_notes,
    delete_notes,
    find_cards,
    find_notes,
    note_info,
    notes_to_cards,
    update_notes,
)
from .sync import invoke_action, sync
from .misc import greet


__all__ = [
    "add_from_model",
    "add_notes",
    "cards_info",
    "cards_to_notes",
    "notes_to_cards",
    "create_deck",
    "create_model",
    "delete_decks",
    "delete_media",
    "delete_notes",
    "find_cards",
    "find_notes",
    "greet",
    "get_deck_config",
    "get_media",
    "invoke_action",
    "sync",
    "list_models",
    "list_decks",
    "list_tags",
    "model_info",
    "note_info",
    "save_deck_config",
    "rename_deck",
    "store_media",
    "update_model_styling",
    "update_model_templates",
    "update_notes",
]
