from __future__ import annotations

import os

from fastmcp import FastMCP
try:
    from fastmcp.utilities.inspect import format_mcp_info as _format_mcp_info
except Exception:  # pragma: no cover - fallback when fastmcp utilities unavailable
    _format_mcp_info = None

try:
    from fastapi import Request
    from fastapi.responses import JSONResponse
except Exception:  # pragma: no cover - fallback when fastapi is unavailable
    try:  # pragma: no cover - fallback if only Starlette is available
        from starlette.requests import Request  # type: ignore
    except Exception:  # pragma: no cover - fallback when neither is available
        class Request:  # minimal placeholder for degraded environments
            pass

    try:  # pragma: no cover - prefer Starlette's JSONResponse when available
        from starlette.responses import JSONResponse  # type: ignore
    except Exception:  # pragma: no cover - last-resort JSON response implementation
        class JSONResponse:
            def __init__(
                self,
                content,
                media_type: str = "application/json",
                status_code: int = 200,
                headers: Optional[dict] = None,
            ) -> None:
                self.content = content
                self.media_type = media_type
                self.status_code = status_code
                self._body = self._render_body(content)
                base_headers = headers.copy() if headers else {}
                self.headers = {k.lower(): str(v) for k, v in base_headers.items()}
                self.headers.setdefault("content-type", self.media_type)
                self.headers.setdefault("content-length", str(len(self._body)))

            @staticmethod
            def _render_body(content) -> bytes:
                if isinstance(content, (bytes, bytearray)):
                    return bytes(content)
                if isinstance(content, str):
                    return content.encode("utf-8")
                return json.dumps(content).encode("utf-8")

            async def __call__(self, scope, receive, send):  # pragma: no cover - used only in degraded environments
                if scope.get("type") != "http":
                    raise RuntimeError("JSONResponse only supports HTTP requests")

                headers = [
                    (name.encode("latin-1"), value.encode("latin-1"))
                    for name, value in self.headers.items()
                ]

                await send(
                    {
                        "type": "http.response.start",
                        "status": self.status_code,
                        "headers": headers,
                    }
                )
                await send(
                    {
                        "type": "http.response.body",
                        "body": self._body,
                        "more_body": False,
                    }
                )
try:
    from pydantic import BaseModel, Field, constr, AnyHttpUrl, ConfigDict
except ImportError:  # pragma: no cover - поддержка Pydantic v1 без ConfigDict
    from pydantic import BaseModel, Field, constr, AnyHttpUrl  # type: ignore

    ConfigDict = None  # type: ignore
from typing import Dict, List, Optional, Tuple

import inspect
import json

import httpx
import base64
import uuid
import re
import hashlib
from io import BytesIO
from PIL import Image

app = FastMCP("anki-mcp")


def _env_default(name: str, fallback: str) -> str:
    value = os.environ.get(name)
    if value is None:
        return fallback
    trimmed = value.strip()
    return trimmed or fallback


DEFAULT_DECK = _env_default("ANKI_DEFAULT_DECK", "Default")
DEFAULT_MODEL = _env_default("ANKI_DEFAULT_MODEL", "Basic")

_ENVIRONMENT_INFO = {"defaultDeck": DEFAULT_DECK, "defaultModel": DEFAULT_MODEL}


async def _build_manifest() -> dict:
    """Собирает MCP-манифест, используя fastmcp или запасную реализацию."""

    if _format_mcp_info is not None:
        manifest = _format_mcp_info(app)
        if inspect.isawaitable(manifest):
            manifest = await manifest
        if isinstance(manifest, (bytes, bytearray)):
            manifest = manifest.decode("utf-8")
        if isinstance(manifest, str):
            manifest = json.loads(manifest)
        return _normalize_manifest(manifest)

    # Запасной вариант для тестов без fastmcp: возвращаем минимально корректную структуру
    return _normalize_manifest({
        "mcp": {"version": "0.1.0"},
        "server": {"name": getattr(app, "name", "anki-mcp")},
        "tools": [],
        "resources": [],
        "prompts": [],
    })


async def _manifest_response() -> JSONResponse:
    manifest = await _build_manifest()
    return JSONResponse(manifest, media_type="application/json")


def _normalize_manifest(manifest: dict) -> dict:
    """Приводит ответ fastmcp к структуре, ожидаемой спецификацией MCP."""

    if "mcp" in manifest and "server" in manifest:
        normalized = dict(manifest)
        env_section = dict(normalized.get("environment", {}))
        env_section.update(_ENVIRONMENT_INFO)
        normalized["environment"] = env_section
        return normalized

    environment = dict(manifest.get("environment", {}))
    environment.update(_ENVIRONMENT_INFO)
    server_info = manifest.get("serverInfo", {})

    normalized: dict = {
        "mcp": {"version": environment.get("mcp") or environment.get("protocol") or "0.1.0"},
        "server": {"name": server_info.get("name") or getattr(app, "name", "anki-mcp")},
        "tools": manifest.get("tools", []),
        "resources": manifest.get("resources", []),
        "prompts": manifest.get("prompts", []),
    }

    if server_info.get("version"):
        normalized["server"]["version"] = server_info["version"]
    if server_info.get("title"):
        normalized["server"]["description"] = server_info["title"]
    if "capabilities" in manifest:
        normalized["capabilities"] = manifest.get("capabilities", {})
    if "resourceTemplates" in manifest:
        normalized["resourceTemplates"] = manifest.get("resourceTemplates", [])
    if environment:
        normalized["environment"] = environment

    return normalized


@app.custom_route("/", methods=["GET"])
async def read_root(request: Request):  # pragma: no cover - trivial wrapper
    return await _manifest_response()


@app.custom_route("/.well-known/mcp.json", methods=["GET"])
async def read_well_known_manifest(request: Request):  # pragma: no cover - trivial wrapper
    return await _manifest_response()

ANKI_URL = "http://127.0.0.1:8765"  # Anki + AnkiConnect must be running


# ======================== СХЕМЫ ========================

class ImageSpec(BaseModel):
    image_base64: Optional[str] = None
    image_url: Optional[AnyHttpUrl] = Field(default=None, alias="url")
    target_field: constr(strip_whitespace=True, min_length=1) = "Back"
    filename: Optional[str] = None
    max_side: int = Field(default=768, ge=1)  # ресайз по длинной стороне

    if ConfigDict is not None:  # pragma: no branch - атрибут существует только в Pydantic v2
        model_config = ConfigDict(populate_by_name=True)
    else:  # pragma: no cover - используется только в Pydantic v1
        class Config:
            allow_population_by_field_name = True


class NoteInput(BaseModel):
    # Поля будущей заметки (мы приведём к полям модели)
    fields: Dict[str, str]
    tags: List[str] = Field(default_factory=list)
    images: List[ImageSpec] = Field(default_factory=list)
    dedup_key: Optional[str] = None  # произвольная строка для идемпотентности


class AddNotesArgs(BaseModel):
    deck: constr(strip_whitespace=True, min_length=1) = Field(default=DEFAULT_DECK)
    model: constr(strip_whitespace=True, min_length=1) = Field(default=DEFAULT_MODEL)  # "Basic" / "Cloze" / кастомная
    notes: List[NoteInput] = Field(min_length=1)


class AddNotesResult(BaseModel):
    added: int
    skipped: int
    details: List[dict] = Field(default_factory=list)


class ModelInfo(BaseModel):
    model: str
    fields: List[str]
    templates: Dict[str, Dict[str, str]]  # {"Card 1": {"Front":"...", "Back":"..."}}
    styling: str


# ======================== УТИЛИТЫ ========================

async def anki_call(action: str, params: dict):
    payload = {"action": action, "version": 6, "params": params}
    async with httpx.AsyncClient(timeout=25) as c:
        r = await c.post(ANKI_URL, json=payload)
        r.raise_for_status()
        data = r.json()
        if data.get("error"):
            raise RuntimeError(f"Anki error: {data['error']}")
        return data["result"]


async def store_media_file(filename: str, data_b64: str):
    return await anki_call("storeMediaFile", {"filename": filename, "data": data_b64})


async def fetch_image_as_base64(url: str, max_side: int) -> str:
    if max_side < 1:
        raise ValueError("max_side must be at least 1")

    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as c:
        r = await c.get(url)
        r.raise_for_status()
        content = r.content

    # лёгкое сжатие/ресайз (если распознаётся формат)
    try:
        im = Image.open(BytesIO(content)).convert("RGB")
        w, h = im.size
        scale = max(w, h) / max_side if max(w, h) > max_side else 1.0
        if scale > 1.0:
            # гарантируем положительные размеры даже при очень узких/низких изображениях
            new_w = max(1, round(w / scale))
            new_h = max(1, round(h / scale))
            im = im.resize((new_w, new_h))
        buf = BytesIO()
        im.save(buf, format="JPEG", quality=85)
        content = buf.getvalue()
    except Exception:
        # если Pillow не смог — отправим как есть
        pass

    return base64.b64encode(content).decode("ascii")


def ensure_img_tag(existing: str, fname: str) -> str:
    tag = f'<div><img src="{fname}" style="max-width:100%;height:auto"/></div>'
    return (existing or "") + ("\n\n" if existing else "") + tag


DATA_URL_RE = re.compile(r"^data:image/([a-zA-Z0-9+.\-]+);base64,(.+)$")


def ext_from_mime(mime_subtype: str) -> str:
    st = mime_subtype.lower()
    if st in ("jpeg", "jpg", "pjpeg"):
        return "jpg"
    if st in ("png", "x-png"):
        return "png"
    if st in ("webp",):
        return "webp"
    if st in ("gif",):
        return "gif"
    # fallback
    return "png"


def sanitize_image_payload(payload: str) -> Tuple[str, Optional[str]]:
    """Нормализует строку Base64 или data URL и подсказывает расширение."""

    trimmed = (payload or "").strip()
    if not trimmed:
        raise ValueError("image payload is empty")

    m = DATA_URL_RE.match(trimmed)
    if m:
        mime_subtype, b64_payload = m.group(1), m.group(2).strip()
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


async def process_data_urls_in_fields(fields: Dict[str, str], results: List[dict], note_index: int):
    """
    Находит в строковых полях data URL вида data:image/...;base64,AAA...
    Сохраняет как медиа-файл в Anki и заменяет значение поля на имя файла.
    """
    for key, value in list(fields.items()):
        if not isinstance(value, str):
            continue
        value = value.strip()
        m = DATA_URL_RE.match(value)
        if not m:
            continue

        try:
            clean_b64, ext_hint = sanitize_image_payload(value)
            raw = base64.b64decode(clean_b64, validate=True)
            # имя по хэшу содержимого
            digest = hashlib.sha1(raw).hexdigest()  # компактно и детерминировано
            mime_subtype = m.group(1)
            extension = ext_hint or ext_from_mime(mime_subtype)
            fname = f"img_{digest}.{extension}"
            # сохраняем
            await store_media_file(fname, clean_b64)
            # подменяем поле на имя файла (шаблон {{Image}} сам подставит <img src="{{Image}}">)
            fields[key] = fname
            results.append({"index": note_index, "info": f"data_url_saved:{key}->{fname}"})
        except Exception as e:
            results.append({"index": note_index, "warn": f"data_url_failed:{key}: {e}"})


async def get_model_fields_templates(model: str) -> Tuple[List[str], Dict[str, Dict[str, str]], str]:
    """
    Возвращает (fields, templates, styling) для модели.
    """
    fields = await anki_call("modelFieldNames", {"modelName": model})
    templates = await anki_call("modelTemplates", {"modelName": model})
    styling = await anki_call("modelStyling", {"modelName": model})
    return fields, templates, styling.get("css", "")


def normalize_fields_for_model(
    user_fields: Dict[str, str], model_fields: List[str]
) -> Tuple[Dict[str, str], int, List[str]]:
    """
    Оставляем только поля модели и заполняем недостающие пустыми строками.
    Без учёта регистра на входе.
    """
    normalized: Dict[str, str] = {}
    lower_map = {k.lower(): k for k in user_fields.keys()}
    matched_keys: List[str] = []
    for mf in model_fields:
        key = lower_map.get(mf.lower())
        if key:
            normalized[mf] = user_fields.get(key, "")
            matched_keys.append(key)
        else:
            normalized[mf] = ""

    unknown_fields = [k for k in user_fields.keys() if k not in matched_keys]
    return normalized, len(matched_keys), sorted(unknown_fields)


# ======================== ИНСТРУМЕНТЫ ========================

@app.tool(name="anki.model_info")
async def model_info(model: str = DEFAULT_MODEL) -> ModelInfo:
    """
    Возвращает актуальные поля, шаблоны (Front/Back) и CSS для заданной модели Anki.
    """
    fields, templates, css = await get_model_fields_templates(model)
    return ModelInfo(model=model, fields=fields, templates=templates, styling=css)


@app.tool(name="anki.add_from_model")
async def add_from_model(deck: str = DEFAULT_DECK, model: str = DEFAULT_MODEL, items: Optional[List[NoteInput]] = None) -> AddNotesResult:
    """
    Добавляет заметки, предварительно запрашивая действующие поля модели.
    Дополнительно:
    - Обрабатывает data URL в полях (например, Image="data:image/png;base64,..."):
      файл сохраняется в медиа, поле заменяется на имя файла (img_xxx.png).
    - Поддерживает images[] (url/base64) c подстановкой <img> в target_field.
    """
    if items is None:
        raise ValueError("items must be provided")

    await anki_call("createDeck", {"deck": deck})

    model_fields, _, _ = await get_model_fields_templates(model)

    notes_payload: List[dict] = []
    results: List[dict] = []
    added = skipped = 0

    for i, note in enumerate(items):
        # 1) нормализуем поля под модель
        fields, matched_count, unknown_fields = normalize_fields_for_model(
            note.fields, model_fields
        )

        if matched_count == 0 or not fields.get(model_fields[0]):
            expected = ", ".join(repr(name) for name in model_fields)
            provided = ", ".join(repr(name) for name in unknown_fields)
            raise ValueError(
                "Unknown note fields: "
                f"[{provided}]"  # квадратные скобки для единообразия с ожиданиями теста
                f". Expected fields: [{expected}]. "
                f"Ensure required field '{model_fields[0]}' is provided."
            )

        # 2) data URL внутри полей (например, поле Image)
        await process_data_urls_in_fields(fields, results, i)

        # 3) поддержка images[] (старый механизм вставки <img>)
        for img in note.images:
            ext_hint: Optional[str] = None
            if img.image_base64:
                try:
                    data_b64, ext_hint = sanitize_image_payload(img.image_base64)
                except ValueError as e:
                    results.append({"index": i, "warn": f"invalid_image_base64: {e}"})
                    continue
            elif img.image_url:
                try:
                    data_b64 = await fetch_image_as_base64(str(img.image_url), img.max_side)
                except Exception as e:
                    results.append({"index": i, "warn": f"fetch_image_failed: {e}"})
                    continue
            else:
                results.append({"index": i, "warn": "no_image_provided"})
                continue

            fname = img.filename or f"{uuid.uuid4().hex}.{ext_hint or 'jpg'}"
            try:
                await store_media_file(fname, data_b64)
                prev = fields.get(img.target_field, "")
                fields[img.target_field] = ensure_img_tag(prev, fname)
            except Exception as e:
                results.append({"index": i, "warn": f"store_media_failed: {e}"})

        notes_payload.append({
            "deckName": deck,
            "modelName": model,
            "fields": fields,
            "tags": note.tags,
            "options": {"allowDuplicate": False}
        })

    # 4) основной вызов Anki
    try:
        res = await anki_call("addNotes", {"notes": notes_payload})
        for idx, note_id in enumerate(res):
            dedup_key = items[idx].dedup_key
            if note_id is None:
                skipped += 1
                detail = {"index": idx, "status": "duplicate"}
                if dedup_key is not None:
                    detail["dedup_key"] = dedup_key
                results.append(detail)
            else:
                added += 1
                details = {"index": idx, "status": "ok", "noteId": note_id}
                if dedup_key is not None:
                    details["dedup_key"] = dedup_key
                results.append(details)
    except Exception as e:
        raise RuntimeError(f"addNotes_failed: {e}") from e

    return AddNotesResult(added=added, skipped=skipped, details=results)


# Низкоуровневый батч без авто-подтягивания полей модели (оставил для совместимости)
@app.tool(name="anki.add_notes")
async def add_notes(args: AddNotesArgs) -> AddNotesResult:
    await anki_call("createDeck", {"deck": args.deck})

    notes_payload: List[dict] = []
    results: List[dict] = []
    added = skipped = 0

    for i, note in enumerate(args.notes):
        fields = {k: (v or "") for k, v in note.fields.items()}

        # data URL прямо в полях
        await process_data_urls_in_fields(fields, results, i)

        # images[] как раньше
        for img in note.images:
            ext_hint: Optional[str] = None
            if img.image_base64:
                try:
                    data_b64, ext_hint = sanitize_image_payload(img.image_base64)
                except ValueError as e:
                    results.append({"index": i, "warn": f"invalid_image_base64: {e}"})
                    continue
            elif img.image_url:
                try:
                    data_b64 = await fetch_image_as_base64(str(img.image_url), img.max_side)
                except Exception as e:
                    results.append({"index": i, "warn": f"fetch_image_failed: {e}"})
                    continue
            else:
                results.append({"index": i, "warn": "no_image_provided"})
                continue

            fname = img.filename or f"{uuid.uuid4().hex}.{ext_hint or 'jpg'}"
            try:
                await store_media_file(fname, data_b64)
                prev = fields.get(img.target_field, "")
                fields[img.target_field] = ensure_img_tag(prev, fname)
            except Exception as e:
                results.append({"index": i, "warn": f"store_media_failed: {e}"})

        notes_payload.append({
            "deckName": args.deck,
            "modelName": args.model,
            "fields": fields,
            "tags": note.tags,
            "options": {"allowDuplicate": False}
        })

    try:
        res = await anki_call("addNotes", {"notes": notes_payload})
        for idx, note_id in enumerate(res):
            dedup_key = args.notes[idx].dedup_key
            if note_id is None:
                skipped += 1
                detail = {"index": idx, "status": "duplicate"}
                if dedup_key is not None:
                    detail["dedup_key"] = dedup_key
                results.append(detail)
            else:
                added += 1
                detail = {"index": idx, "status": "ok", "noteId": note_id}
                if dedup_key is not None:
                    detail["dedup_key"] = dedup_key
                results.append(detail)
    except Exception as e:
        raise RuntimeError(f"addNotes_failed: {e}") from e

    return AddNotesResult(added=added, skipped=skipped, details=results)


# Пинг
@app.tool()
def greet(name: str) -> str:
    return f"Привет, {name}! Я твой MCP-сервер."
