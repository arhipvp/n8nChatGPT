"""Совместимый фасад над специализированными подсистемами сервисов."""

from __future__ import annotations

from typing import Dict, List, Tuple

from .. import config

from . import client as client_services
from . import media as media_services
from . import notes as notes_services

_MODULE_EXPORTS: Tuple[object, ...] = (
    client_services,
    media_services,
    notes_services,
)


def __getattr__(name: str):  # pragma: no cover - простой прокси
    if name == "ANKI_URL":
        return config.ANKI_URL
    for module in _MODULE_EXPORTS:
        if hasattr(module, name):
            return getattr(module, name)
    raise AttributeError(f"module 'anki_mcp.services.anki' has no attribute {name!r}")


def __dir__() -> List[str]:  # pragma: no cover - вспомогательный экспорт
    dynamic: List[str] = []
    for module in _MODULE_EXPORTS:
        dynamic.extend(getattr(module, "__all__", []) or dir(module))
    dynamic.extend(["ANKI_URL", "get_model_field_names", "get_model_fields_templates"])
    return sorted(set(dynamic))


async def get_model_fields_templates(
    model: str,
) -> Tuple[List[str], Dict[str, Dict[str, str]], str]:
    fields = await client_services.anki_call("modelFieldNames", {"modelName": model})
    templates = await client_services.anki_call("modelTemplates", {"modelName": model})
    styling = await client_services.anki_call("modelStyling", {"modelName": model})
    return fields, templates, styling.get("css", "")


async def get_model_field_names(model: str) -> List[str]:
    return await client_services.anki_call("modelFieldNames", {"modelName": model})


__all__ = [
    "ANKI_URL",
    "ANCHOR_TAG_RE",
    "DATA_URL_INLINE_RE",
    "DATA_URL_RE",
    "IMG_TAG_TEMPLATE",
    "anki_call",
    "auto_link_urls",
    "build_img_tag",
    "ensure_img_tag",
    "ext_from_mime",
    "fetch_image_as_base64",
    "get_model_field_names",
    "get_model_fields_templates",
    "httpx",
    "normalize_and_validate_note_fields",
    "normalize_fields_for_model",
    "normalize_notes_info",
    "process_data_urls_in_fields",
    "sanitize_image_payload",
    "store_media_file",
]
