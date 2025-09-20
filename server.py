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

from typing import Any, Dict, List, Optional, Tuple, Type, TypeVar, Union


try:  # pragma: no cover - модельный валидатор есть только в Pydantic v2
    from pydantic import model_validator  # type: ignore
except ImportError:  # pragma: no cover - Pydantic v1
    model_validator = None  # type: ignore

try:  # pragma: no cover - Pydantic v2 сохраняет root_validator для совместимости
    from pydantic import root_validator  # type: ignore
except ImportError:  # pragma: no cover - Pydantic v2 без root_validator (теоретически)
    root_validator = None  # type: ignore
from typing import Dict, List, Optional, Tuple


import inspect
import json

import base64
import uuid
import re
import hashlib
from io import BytesIO
from PIL import Image
import httpx

_NOTE_RESERVED_TOP_LEVEL_KEYS = {"tags", "images", "dedup_key"}


def _coerce_note_fields(cls, values):
    """Извлекает плоские поля в NoteInput.fields до стандартной валидации."""

    if not isinstance(values, dict):  # pragma: no cover - для совместимости с Pydantic v1
        return values

    if "fields" in values:
        return values

    candidate_items = {
        key: values[key]
        for key in list(values.keys())
        if key not in _NOTE_RESERVED_TOP_LEVEL_KEYS
    }

    if not candidate_items:
        raise ValueError(
            "Каждый элемент items должен содержать объект fields с полями заметки"
        )

    normalized = {k: v for k, v in values.items() if k not in candidate_items}
    normalized["fields"] = candidate_items
    return normalized

app = FastMCP("anki-mcp")

if not hasattr(app, "action"):
    setattr(app, "action", app.tool)


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


DEFAULT_DECK = _env_default("ANKI_DEFAULT_DECK", "Default")
DEFAULT_MODEL = _env_default("ANKI_DEFAULT_MODEL", "Basic")
SEARCH_API_URL = _env_optional("SEARCH_API_URL")
SEARCH_API_KEY = _env_optional("SEARCH_API_KEY")

_ENVIRONMENT_INFO = {"defaultDeck": DEFAULT_DECK, "defaultModel": DEFAULT_MODEL}


T_Model = TypeVar("T_Model", bound=BaseModel)


def _model_validate(model: Type[T_Model], data: Any) -> T_Model:
    if hasattr(model, "model_validate"):
        return model.model_validate(data)  # type: ignore[attr-defined]
    return model.parse_obj(data)  # type: ignore[attr-defined]


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
        return _ensure_search_capability(normalized)

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

    return _ensure_search_capability(normalized)


def _ensure_search_capability(manifest: dict) -> dict:
    capabilities = dict(manifest.get("capabilities", {}))
    existing_search = capabilities.get("search")
    if isinstance(existing_search, dict):
        updated_search = dict(existing_search)
        updated_search["enabled"] = True
    else:
        updated_search = {"enabled": True}
    capabilities["search"] = updated_search
    manifest["capabilities"] = capabilities
    return manifest


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

    if model_validator is not None:  # pragma: no branch - конкретная ветка зависит от версии Pydantic

        @model_validator(mode="before")  # type: ignore[misc]
        @classmethod
        def _ensure_fields(cls, values):
            return _coerce_note_fields(cls, values)

    elif root_validator is not None:  # pragma: no cover - fallback для Pydantic v1

        @root_validator(pre=True)
        def _ensure_fields(cls, values):  # type: ignore[override]
            return _coerce_note_fields(cls, values)


class AddNotesArgs(BaseModel):
    deck: constr(strip_whitespace=True, min_length=1) = Field(default=DEFAULT_DECK)
    model: constr(strip_whitespace=True, min_length=1) = Field(default=DEFAULT_MODEL)  # "Basic" / "Cloze" / кастомная
    notes: List[NoteInput] = Field(min_length=1)


class AddNotesResult(BaseModel):
    added: int
    skipped: int
    details: List[dict] = Field(default_factory=list)


class NoteInfoArgs(BaseModel):
    note_ids: List[int] = Field(min_length=1, alias="noteIds")

    if ConfigDict is not None:  # pragma: no branch
        model_config = ConfigDict(populate_by_name=True)
    else:  # pragma: no cover
        class Config:
            allow_population_by_field_name = True


class NoteInfo(BaseModel):
    note_id: int = Field(alias="noteId")
    model_name: Optional[str] = Field(default=None, alias="modelName")
    deck_name: Optional[str] = Field(default=None, alias="deckName")
    tags: List[str] = Field(default_factory=list)
    fields: Dict[str, str] = Field(default_factory=dict)
    cards: List[int] = Field(default_factory=list)

    if ConfigDict is not None:  # pragma: no branch
        model_config = ConfigDict(populate_by_name=True)
    else:  # pragma: no cover
        class Config:
            allow_population_by_field_name = True


class NoteInfoResponse(BaseModel):
    notes: List[Optional[NoteInfo]] = Field(default_factory=list)


class ModelInfo(BaseModel):
    model: str
    fields: List[str]
    templates: Dict[str, Dict[str, str]]  # {"Card 1": {"Front":"...", "Back":"..."}}
    styling: str


class SearchRequest(BaseModel):
    query: constr(strip_whitespace=True, min_length=1)
    limit: Optional[int] = Field(default=None, ge=1)
    cursor: Optional[constr(strip_whitespace=True, min_length=1)] = None

    if ConfigDict is not None:  # pragma: no branch
        model_config = ConfigDict(populate_by_name=True)
    else:  # pragma: no cover
        class Config:
            allow_population_by_field_name = True


class SearchResult(BaseModel):
    title: Optional[str] = None
    url: Optional[AnyHttpUrl] = None
    snippet: Optional[str] = None
    content: Optional[str] = None
    score: Optional[float] = None

    if ConfigDict is not None:  # pragma: no branch
        model_config = ConfigDict(extra="allow")
    else:  # pragma: no cover
        class Config:
            extra = "allow"


class SearchResponse(BaseModel):
    results: List[SearchResult] = Field(default_factory=list)
    next_cursor: Optional[str] = Field(default=None, alias="nextCursor")

    if ConfigDict is not None:  # pragma: no branch
        model_config = ConfigDict(populate_by_name=True)
    else:  # pragma: no cover
        class Config:
            allow_population_by_field_name = True


def _normalize_search_payload(raw_payload: Any) -> dict:
    if not isinstance(raw_payload, dict):
        raise ValueError("Search API response must be a JSON object")

    payload = dict(raw_payload)
    results = payload.get("results")
    if results is None and "items" in payload:
        results = payload["items"]

    if results is None:
        raise ValueError("Search API response is missing 'results'")
    if not isinstance(results, list):
        raise ValueError("Search API 'results' must be a list")

    next_cursor = payload.get("nextCursor")
    if next_cursor is None:
        next_cursor = payload.get("next_cursor")
    if next_cursor is None:
        next_cursor = payload.get("nextPageToken") or payload.get("next_page_token")

    normalized: Dict[str, Any] = {"results": results}
    if next_cursor is not None:
        normalized["nextCursor"] = next_cursor
    return normalized


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


IMG_TAG_TEMPLATE = '<div><img src="{src}" style="max-width:100%;height:auto"/></div>'


def build_img_tag(fname: str) -> str:
    return IMG_TAG_TEMPLATE.format(src=fname)


def ensure_img_tag(existing: str, fname: str) -> str:
    existing = existing or ""
    tag = build_img_tag(fname)
    if re.search(rf'src=["\']{re.escape(fname)}["\']', existing, re.IGNORECASE):
        return existing

    trimmed = existing.rstrip()
    if not trimmed:
        return tag
    return f"{trimmed}\n\n{tag}"


DATA_URL_RE = re.compile(r"^data:image/([a-zA-Z0-9+.\-]+);base64,(.+)$", re.IGNORECASE)
DATA_URL_INLINE_RE = re.compile(
    r"data:image/([a-zA-Z0-9+.\-]+);base64,([a-zA-Z0-9+/=]+)", re.IGNORECASE
)


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


async def process_data_urls_in_fields(
    fields: Dict[str, str], results: List[dict], note_index: int
):
    """Находит data URL в строковых полях, сохраняет их как медиа и вставляет `<img>`.

    Поле приводится к тому же формату, что и при обработке `images[]`, при этом
    сохраняется произвольный текст и уже добавленные теги `<img>` не дублируются.
    """

    for key, value in list(fields.items()):
        if not isinstance(value, str):
            continue

        matches = list(DATA_URL_INLINE_RE.finditer(value))
        if not matches:
            trimmed = value.strip()
            m = DATA_URL_RE.match(trimmed)
            matches = [m] if m else []
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
                fname = f"img_{digest}.{extension}"
                await store_media_file(fname, clean_b64)
                saved_files.append(fname)
                results.append(
                    {"index": note_index, "info": f"data_url_saved:{key}->{fname}"}
                )
            except Exception as e:
                results.append({"index": note_index, "warn": f"data_url_failed:{key}: {e}"})
                rebuilt.append(value[cursor : match.end()])
                cursor = match.end()
                continue

            rebuilt.append(value[cursor : match.start()])
            cursor = match.end()

        rebuilt.append(value[cursor:])
        new_value = "".join(rebuilt)
        clean_text = new_value.strip()
        for fname in saved_files:
            clean_text = ensure_img_tag(clean_text, fname)

        fields[key] = clean_text


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


def normalize_and_validate_note_fields(
    user_fields: Dict[str, str], model_fields: List[str]
) -> Dict[str, str]:
    fields, matched_count, unknown_fields = normalize_fields_for_model(
        user_fields, model_fields
    )

    if not model_fields:
        raise ValueError("Model has no fields configured")

    if matched_count == 0 or not fields.get(model_fields[0]):
        expected = ", ".join(repr(name) for name in model_fields)
        provided = ", ".join(repr(name) for name in unknown_fields)
        raise ValueError(
            "Unknown note fields: "
            f"[{provided}]"  # квадратные скобки для единообразия с ожиданиями теста
            f". Expected fields: [{expected}]. "
            f"Ensure required field '{model_fields[0]}' is provided."
        )

    return fields


def _normalize_note_fields_payload(raw_fields: Any) -> Dict[str, str]:
    if not isinstance(raw_fields, dict):
        return {}

    normalized: Dict[str, str] = {}
    for key, value in raw_fields.items():
        if isinstance(value, dict) and "value" in value:
            candidate = value.get("value")
        else:
            candidate = value

        if candidate is None:
            normalized_value = ""
        elif isinstance(candidate, str):
            normalized_value = candidate
        else:
            normalized_value = str(candidate)

        normalized[str(key)] = normalized_value

    return normalized


def _normalize_note_tags(raw_tags: Any) -> List[str]:
    if not isinstance(raw_tags, list):
        return []

    tags: List[str] = []
    for tag in raw_tags:
        if tag is None:
            continue
        if isinstance(tag, str):
            trimmed = tag.strip()
            if trimmed:
                tags.append(trimmed)
        else:
            tags.append(str(tag))
    return tags


def _normalize_note_cards(raw_cards: Any) -> List[int]:
    if not isinstance(raw_cards, list):
        return []

    cards: List[int] = []
    for card in raw_cards:
        if card is None:
            continue
        if isinstance(card, int):
            cards.append(card)
            continue
        if isinstance(card, float):
            cards.append(int(card))
            continue
        if isinstance(card, str):
            stripped = card.strip()
            if not stripped:
                continue
            try:
                cards.append(int(stripped))
            except ValueError:
                continue
    return cards


def _normalize_note_entry(raw_note: Any, index: int) -> Optional[NoteInfo]:
    if raw_note is None:
        return None
    if not isinstance(raw_note, dict):
        raise ValueError(f"notesInfo[{index}] must be an object or null")

    note_id_raw = raw_note.get("noteId")
    if isinstance(note_id_raw, int):
        note_id = note_id_raw
    elif isinstance(note_id_raw, str):
        stripped = note_id_raw.strip()
        if not stripped:
            raise ValueError(f"notesInfo[{index}].noteId is empty")
        try:
            note_id = int(stripped)
        except ValueError as exc:
            raise ValueError(
                f"notesInfo[{index}].noteId must be an integer, got {note_id_raw!r}"
            ) from exc
    else:
        raise ValueError(
            f"notesInfo[{index}].noteId must be an integer, got {note_id_raw!r}"
        )

    payload = {
        "noteId": note_id,
        "modelName": raw_note.get("modelName"),
        "deckName": raw_note.get("deckName"),
        "tags": _normalize_note_tags(raw_note.get("tags")),
        "fields": _normalize_note_fields_payload(raw_note.get("fields")),
        "cards": _normalize_note_cards(raw_note.get("cards")),
    }

    return _model_validate(NoteInfo, payload)


def _normalize_notes_info(raw_notes: Any) -> List[Optional[NoteInfo]]:
    if not isinstance(raw_notes, list):
        raise ValueError("notesInfo response must be a list")

    normalized: List[Optional[NoteInfo]] = []
    for index, raw_note in enumerate(raw_notes):
        normalized.append(_normalize_note_entry(raw_note, index))
    return normalized


# ======================== ДЕЙСТВИЯ ========================


@app.action(name="search")
async def search(request: SearchRequest) -> SearchResponse:
    if not SEARCH_API_URL:
        raise RuntimeError("SEARCH_API_URL is not configured")

    payload: Dict[str, Any] = {"query": request.query}
    if request.limit is not None:
        payload["limit"] = request.limit
    if request.cursor is not None:
        payload["cursor"] = request.cursor

    headers: Dict[str, str] = {}
    if SEARCH_API_KEY:
        headers["Authorization"] = f"Bearer {SEARCH_API_KEY}"

    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(
            SEARCH_API_URL,
            json=payload,
            headers=headers or None,
        )

    response.raise_for_status()
    normalized_payload = _normalize_search_payload(response.json())
    return _model_validate(SearchResponse, normalized_payload)


# ======================== ИНСТРУМЕНТЫ ========================


@app.tool(name="anki.note_info")
async def note_info(args: NoteInfoArgs) -> NoteInfoResponse:
    raw_notes = await anki_call("notesInfo", {"notes": args.note_ids})
    normalized = _normalize_notes_info(raw_notes)
    return NoteInfoResponse(notes=normalized)


@app.tool(name="anki.model_info")
async def model_info(model: str = DEFAULT_MODEL) -> ModelInfo:
    """
    Возвращает актуальные поля, шаблоны (Front/Back) и CSS для заданной модели Anki.
    """
    fields, templates, css = await get_model_fields_templates(model)
    return ModelInfo(model=model, fields=fields, templates=templates, styling=css)


@app.tool(name="anki.add_from_model")
async def add_from_model(
    deck: str = DEFAULT_DECK,
    model: str = DEFAULT_MODEL,
    items: Optional[List[Union[NoteInput, Dict[str, str]]]] = None,
) -> AddNotesResult:
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
    field_aliases = {field.lower(): field for field in model_fields}

    normalized_items: List[NoteInput] = []
    for index, raw_item in enumerate(items):
        if isinstance(raw_item, NoteInput):
            note = raw_item
        elif isinstance(raw_item, dict):
            payload: Dict[str, Any]
            if "fields" in raw_item:
                payload = raw_item  # type: ignore[assignment]
            else:
                candidate_fields = {
                    key: raw_item[key]
                    for key in raw_item.keys()
                    if key not in _NOTE_RESERVED_TOP_LEVEL_KEYS
                }
                if not candidate_fields:
                    raise ValueError(
                        "Каждая заметка должна содержать хотя бы одно поле, например {'Front': 'Question'}."
                    )

                payload = {
                    "fields": candidate_fields,
                }
                for key in _NOTE_RESERVED_TOP_LEVEL_KEYS:
                    if key in raw_item:
                        payload[key] = raw_item[key]

            try:
                note = _model_validate(NoteInput, payload)
            except Exception as exc:  # pragma: no cover - защитный хэндлинг
                raise ValueError(f"Invalid note at index {index}: {exc}") from exc
        else:
            raise TypeError(
                f"items[{index}] must be NoteInput or dict, got {type(raw_item).__name__}"
            )

        normalized_items.append(note)

    notes_payload: List[dict] = []
    results: List[dict] = []
    added = skipped = 0

    for i, note in enumerate(normalized_items):
        # 1) нормализуем поля под модель с валидацией
        fields = normalize_and_validate_note_fields(note.fields, model_fields)

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
            canonical_target = field_aliases.get(img.target_field.lower())
            if not canonical_target:
                results.append(
                    {
                        "index": i,
                        "warn": "unknown_target_field",
                        "field": img.target_field,
                    }
                )
                continue
            try:
                await store_media_file(fname, data_b64)
                prev = fields[canonical_target]
                fields[canonical_target] = ensure_img_tag(prev, fname)
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
            dedup_key = normalized_items[idx].dedup_key
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

    model_fields, _, _ = await get_model_fields_templates(args.model)

    canonical_field_map = {field.lower(): field for field in model_fields}

    notes_payload: List[dict] = []
    results: List[dict] = []
    added = skipped = 0
    normalized_notes: List[NoteInput] = list(args.notes)

    for i, note in enumerate(normalized_notes):
        fields = normalize_and_validate_note_fields(note.fields, model_fields)

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
            canonical_target = canonical_field_map.get(img.target_field.lower())
            if not canonical_target:
                allowed_fields = ", ".join(repr(name) for name in model_fields)
                raise ValueError(
                    "Unknown image target field "
                    f"{img.target_field!r} for note index {i}. "
                    f"Allowed fields: [{allowed_fields}]"
                )
            try:
                await store_media_file(fname, data_b64)
                prev = fields[canonical_target]
                fields[canonical_target] = ensure_img_tag(prev, fname)
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
            dedup_key = normalized_notes[idx].dedup_key
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
