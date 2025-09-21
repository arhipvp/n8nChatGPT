"""Инструменты работы с медиа."""

from __future__ import annotations

import base64
import binascii
from typing import Any, Dict, Mapping, Optional, Union

from .. import app
from ..compat import model_validate
from ..schemas import DeleteMediaArgs, MediaRequest, MediaResponse, StoreMediaArgs
from ..services import client as anki_client


def _normalize_media_error(filename: str, exc: Exception) -> Exception:
    message = str(exc)
    lowered = message.lower()
    markers = (
        "not found",
        "does not exist",
        "no such file",
        "missing",
    )
    if any(marker in lowered for marker in markers):
        return FileNotFoundError(f"Media file {filename!r} not found")
    return exc


def _calculate_media_size(data_base64: str) -> Optional[int]:
    try:
        raw = base64.b64decode(data_base64, validate=True)
    except (binascii.Error, ValueError):
        try:
            raw = base64.b64decode(data_base64, validate=False)
        except Exception:
            return None
    return len(raw)


@app.tool(name="anki.get_media")
async def get_media(args: MediaRequest) -> MediaResponse:
    try:
        raw_base64 = await anki_client.anki_call(
            "retrieveMediaFile", {"filename": args.filename}
        )
    except Exception as exc:  # pragma: no cover - конкретные ошибки проверяются тестами
        normalized_exc = _normalize_media_error(args.filename, exc)
        if normalized_exc is exc:
            raise
        raise normalized_exc from exc

    if not isinstance(raw_base64, str):
        raise ValueError("retrieveMediaFile response must be a base64 string")

    size_bytes = _calculate_media_size(raw_base64)
    return MediaResponse(
        filename=args.filename,
        data_base64=raw_base64,
        size_bytes=size_bytes,
    )


@app.tool(name="anki.store_media")
async def store_media(
    args: Union[StoreMediaArgs, Mapping[str, Any]]
) -> Dict[str, Any]:
    if isinstance(args, StoreMediaArgs):
        normalized = args
    else:
        try:
            normalized = model_validate(StoreMediaArgs, args)
        except Exception as exc:
            raise ValueError(f"Invalid store_media arguments: {exc}") from exc

    try:
        try:
            base64.b64decode(normalized.data_base64, validate=True)
        except (binascii.Error, ValueError):
            base64.b64decode(normalized.data_base64, validate=False)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("data_base64 must be valid Base64-encoded string") from exc

    anki_response = await anki_client.store_media_file(
        normalized.filename, normalized.data_base64
    )

    return {
        "filename": normalized.filename,
        "anki_response": anki_response,
    }


@app.tool(name="anki.delete_media")
async def delete_media(args: DeleteMediaArgs) -> Dict[str, Any]:
    try:
        raw_response = await anki_client.anki_call(
            "deleteMediaFile", {"filename": args.filename}
        )
    except Exception as exc:  # pragma: no cover - конкретные ошибки проверяются тестами
        normalized_exc = _normalize_media_error(args.filename, exc)
        if normalized_exc is exc:
            raise
        raise normalized_exc from exc

    deleted: bool
    if isinstance(raw_response, Mapping):
        deleted = bool(raw_response.get("deleted", True))
    elif isinstance(raw_response, list):
        deleted = all(bool(item) for item in raw_response)
    else:
        deleted = raw_response in (None, True)

    return {
        "filename": args.filename,
        "deleted": deleted,
        "anki_response": raw_response,
    }


__all__ = ["get_media", "store_media", "delete_media"]
