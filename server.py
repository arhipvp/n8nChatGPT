from __future__ import annotations

from fastmcp import FastMCP
from pydantic import BaseModel, Field, constr, AnyHttpUrl
from typing import Dict, List, Optional, Tuple

import httpx
import base64
import uuid
import re
import hashlib
from io import BytesIO
from PIL import Image

app = FastMCP("anki-mcp")

ANKI_URL = "http://127.0.0.1:8765"  # Anki + AnkiConnect must be running


# ======================== СХЕМЫ ========================

class ImageSpec(BaseModel):
    image_base64: Optional[str] = None
    image_url: Optional[AnyHttpUrl] = None
    target_field: constr(strip_whitespace=True, min_length=1) = "Back"
    filename: Optional[str] = None
    max_side: int = 768  # ресайз по длинной стороне


class NoteInput(BaseModel):
    # Поля будущей заметки (мы приведём к полям модели)
    fields: Dict[str, str]
    tags: List[str] = Field(default_factory=list)
    images: List[ImageSpec] = Field(default_factory=list)
    dedup_key: Optional[str] = None  # произвольная строка для идемпотентности


class AddNotesArgs(BaseModel):
    deck: constr(strip_whitespace=True, min_length=1)
    model: constr(strip_whitespace=True, min_length=1)  # "Basic" / "Cloze" / кастомная
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
    async with httpx.AsyncClient(timeout=30) as c:
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


async def process_data_urls_in_fields(fields: Dict[str, str], results: List[dict], note_index: int):
    """
    Находит в строковых полях data URL вида data:image/...;base64,AAA...
    Сохраняет как медиа-файл в Anki и заменяет значение поля на имя файла.
    """
    for key, value in list(fields.items()):
        if not isinstance(value, str):
            continue
        m = DATA_URL_RE.match(value.strip())
        if not m:
            continue

        mime_subtype, b64 = m.group(1), m.group(2)
        try:
            # нормализуем, валидируем base64
            raw = base64.b64decode(b64, validate=True)
            # имя по хэшу содержимого
            digest = hashlib.sha1(raw).hexdigest()  # компактно и детерминировано
            fname = f"img_{digest}.{ext_from_mime(mime_subtype)}"
            # сохраняем
            await store_media_file(fname, base64.b64encode(raw).decode("ascii"))
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


def normalize_fields_for_model(user_fields: Dict[str, str], model_fields: List[str]) -> Dict[str, str]:
    """
    Оставляем только поля модели и заполняем недостающие пустыми строками.
    Без учёта регистра на входе.
    """
    normalized = {}
    lower_map = {k.lower(): k for k in user_fields.keys()}
    for mf in model_fields:
        key = lower_map.get(mf.lower())
        normalized[mf] = user_fields.get(key, "") if key else ""
    return normalized


# ======================== ИНСТРУМЕНТЫ ========================

@app.tool(name="anki.model_info")
async def model_info(model: str) -> ModelInfo:
    """
    Возвращает актуальные поля, шаблоны (Front/Back) и CSS для заданной модели Anki.
    """
    fields, templates, css = await get_model_fields_templates(model)
    return ModelInfo(model=model, fields=fields, templates=templates, styling=css)


@app.tool(name="anki.add_from_model")
async def add_from_model(deck: str, model: str, items: List[NoteInput]) -> AddNotesResult:
    """
    Добавляет заметки, предварительно запрашивая действующие поля модели.
    Дополнительно:
    - Обрабатывает data URL в полях (например, Image="data:image/png;base64,..."):
      файл сохраняется в медиа, поле заменяется на имя файла (img_xxx.png).
    - Поддерживает images[] (url/base64) c подстановкой <img> в target_field.
    """
    await anki_call("createDeck", {"deck": deck})

    model_fields, _, _ = await get_model_fields_templates(model)

    notes_payload: List[dict] = []
    results: List[dict] = []
    added = skipped = 0

    for i, note in enumerate(items):
        # 1) нормализуем поля под модель
        fields = normalize_fields_for_model(note.fields, model_fields)

        # 2) data URL внутри полей (например, поле Image)
        await process_data_urls_in_fields(fields, results, i)

        # 3) поддержка images[] (старый механизм вставки <img>)
        for img in note.images:
            fname = img.filename or f"{uuid.uuid4().hex}.jpg"
            if img.image_base64:
                data_b64 = img.image_base64
            elif img.image_url:
                try:
                    data_b64 = await fetch_image_as_base64(str(img.image_url), img.max_side)
                except Exception as e:
                    results.append({"index": i, "warn": f"fetch_image_failed: {e}"})
                    continue
            else:
                results.append({"index": i, "warn": "no_image_provided"})
                continue

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
            if note_id is None:
                skipped += 1
                results.append({"index": idx, "status": "duplicate"})
            else:
                added += 1
                details = {"index": idx, "status": "ok", "noteId": note_id}
                if items[idx].dedup_key:
                    details["dedup_key"] = items[idx].dedup_key
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
            fname = img.filename or f"{uuid.uuid4().hex}.jpg"
            if img.image_base64:
                data_b64 = img.image_base64
            elif img.image_url:
                try:
                    data_b64 = await fetch_image_as_base64(str(img.image_url), img.max_side)
                except Exception as e:
                    results.append({"index": i, "warn": f"fetch_image_failed: {e}"})
                    continue
            else:
                results.append({"index": i, "warn": "no_image_provided"})
                continue

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
            if note_id is None:
                skipped += 1
                results.append({"index": idx, "status": "duplicate"})
            else:
                added += 1
                results.append({"index": idx, "status": "ok", "noteId": note_id})
    except Exception as e:
        raise RuntimeError(f"addNotes_failed: {e}") from e

    return AddNotesResult(added=added, skipped=skipped, details=results)


# Пинг
@app.tool()
def greet(name: str) -> str:
    return f"Привет, {name}! Я твой MCP-сервер."
