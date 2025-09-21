"""Работа с мультимедийными данными и HTML-полями."""

from __future__ import annotations

import base64
import hashlib
import re
from io import BytesIO
from typing import Dict, List, Optional, Tuple

import httpx
from PIL import Image

from . import client as client_services


async def store_media_file(filename: str, data_b64: str):
    return await client_services.store_media_file(filename, data_b64)


IMG_TAG_TEMPLATE = '<div><img src="{src}" style="max-width:100%;height:auto"/></div>'


def build_img_tag(filename: str) -> str:
    return IMG_TAG_TEMPLATE.format(src=filename)


def ensure_img_tag(existing: str, filename: str) -> str:
    existing = existing or ""
    tag = build_img_tag(filename)
    if re.search(rf'src=["\']{re.escape(filename)}["\']', existing, re.IGNORECASE):
        return existing

    trimmed = existing.rstrip()
    if not trimmed:
        return tag
    return f"{trimmed}\n\n{tag}"


ANCHOR_TAG_RE = re.compile(r"<a\b[^>]*>.*?</a>", re.IGNORECASE | re.DOTALL)
URL_RE = re.compile(r"(?P<url>https?://[^\s<>\"']+)", re.IGNORECASE)


def auto_link_urls(text: str) -> str:
    if not text:
        return text or ""

    anchors = [match.span() for match in ANCHOR_TAG_RE.finditer(text)]
    if not anchors:
        return URL_RE.sub(
            lambda match: f'<a href="{match.group("url")}">{match.group("url")}</a>',
            text,
        )

    def _replace(match: re.Match[str]) -> str:
        start = match.start()
        for span_start, span_end in anchors:
            if span_start <= start < span_end:
                return match.group("url")
        url = match.group("url")
        return f'<a href="{url}">{url}</a>'

    return URL_RE.sub(_replace, text)


DATA_URL_RE = re.compile(r"^data:image/([a-zA-Z0-9+.\-]+);base64,(.+)$", re.IGNORECASE)
DATA_URL_INLINE_RE = re.compile(
    r"data:image/([a-zA-Z0-9+.\-]+);base64,([a-zA-Z0-9+/=]+)", re.IGNORECASE
)


def ext_from_mime(mime_subtype: str) -> str:
    subtype = mime_subtype.lower()
    if subtype in ("jpeg", "jpg", "pjpeg"):
        return "jpg"
    if subtype in ("png", "x-png"):
        return "png"
    if subtype in ("webp",):
        return "webp"
    if subtype in ("gif",):
        return "gif"
    return "png"


async def fetch_image_as_base64(url: str, max_side: int) -> str:
    if max_side < 1:
        raise ValueError("max_side must be at least 1")

    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        response = await client.get(url)
        response.raise_for_status()
        content = response.content

    try:
        original = Image.open(BytesIO(content))
        target_format = "JPEG"

        if "A" in (original.getbands() or ()):  # RGBA/LA/etc.
            rgba = original.convert("RGBA")
            background = Image.new("RGB", rgba.size, (255, 255, 255))
            alpha = rgba.getchannel("A")
            background.paste(rgba, mask=alpha)
            image = background
        elif original.mode == "P" and "transparency" in original.info:
            rgba = original.convert("RGBA")
            background = Image.new("RGB", rgba.size, (255, 255, 255))
            alpha = rgba.getchannel("A")
            background.paste(rgba, mask=alpha)
            image = background
        elif original.mode != "RGB":
            image = original.convert("RGB")
        else:
            image = original

        width, height = image.size
        scale = max(width, height) / max_side if max(width, height) > max_side else 1.0
        if scale > 1.0:
            new_width = max(1, round(width / scale))
            new_height = max(1, round(height / scale))
            image = image.resize((new_width, new_height))
        buffer = BytesIO()
        image.save(buffer, format=target_format, quality=85)
        content = buffer.getvalue()
    except Exception:
        pass

    return base64.b64encode(content).decode("ascii")


def sanitize_image_payload(payload: str) -> Tuple[str, Optional[str]]:
    trimmed = (payload or "").strip()
    if not trimmed:
        raise ValueError("image payload is empty")

    match = DATA_URL_RE.match(trimmed)
    if match:
        mime_subtype, b64_payload = match.group(1), match.group(2).strip()
        try:
            raw = base64.b64decode(b64_payload, validate=True)
        except Exception as exc:  # pragma: no cover - error path
            raise ValueError(f"invalid base64 image data: {exc}") from exc
        clean_b64 = base64.b64encode(raw).decode("ascii")
        return clean_b64, ext_from_mime(mime_subtype)

    try:
        raw = base64.b64decode(trimmed, validate=True)
    except Exception as exc:  # pragma: no cover - error path
        raise ValueError(f"invalid base64 image data: {exc}") from exc
    clean_b64 = base64.b64encode(raw).decode("ascii")
    return clean_b64, None


async def process_data_urls_in_fields(
    fields: Dict[str, str], results: List[dict], note_index: int
):
    for key, value in list(fields.items()):
        if not isinstance(value, str):
            continue

        matches = list(DATA_URL_INLINE_RE.finditer(value))
        if not matches:
            trimmed = value.strip()
            match = DATA_URL_RE.match(trimmed)
            matches = [match] if match else []
            if matches:
                value = trimmed
        if not matches:
            continue

        saved_files: List[str] = []
        rebuilt: List[str] = []
        cursor = 0

        for match in matches:
            data_url = match.group(0)
            try:
                clean_b64, ext_hint = sanitize_image_payload(data_url)
                raw = base64.b64decode(clean_b64, validate=True)
                digest = hashlib.sha1(raw).hexdigest()
                mime_subtype = match.group(1) if match.lastindex else None
                extension = ext_hint or (
                    ext_from_mime(mime_subtype) if mime_subtype else "png"
                )
                filename = f"img_{digest}.{extension}"
                await store_media_file(filename, clean_b64)
                saved_files.append(filename)
                results.append({"index": note_index, "info": f"data_url_saved:{key}->{filename}"})
            except Exception as exc:
                results.append({"index": note_index, "warn": f"data_url_failed:{key}: {exc}"})
                rebuilt.append(value[cursor : match.end()])
                cursor = match.end()
                continue

            rebuilt.append(value[cursor : match.start()])
            cursor = match.end()

        rebuilt.append(value[cursor:])
        new_value = "".join(rebuilt)
        clean_text = new_value.strip()
        for filename in saved_files:
            clean_text = ensure_img_tag(clean_text, filename)

        fields[key] = clean_text


__all__ = [
    "ANCHOR_TAG_RE",
    "DATA_URL_INLINE_RE",
    "DATA_URL_RE",
    "IMG_TAG_TEMPLATE",
    "auto_link_urls",
    "build_img_tag",
    "ensure_img_tag",
    "ext_from_mime",
    "fetch_image_as_base64",
    "httpx",
    "process_data_urls_in_fields",
    "store_media_file",
    "sanitize_image_payload",
]
