"""Формирование MCP-манифеста и HTTP-маршруты."""

from __future__ import annotations

import inspect
import json
from typing import Any, List, Mapping, Optional, Tuple

try:  # pragma: no cover - модуль может отсутствовать в среде тестов
    from fastmcp.utilities.inspect import format_mcp_info as _format_mcp_info  # type: ignore
except Exception:  # pragma: no cover - используем fallback
    _format_mcp_info = None

from . import app, config
from .compat import JSONResponse, Request


async def _ensure_awaitable(value):
    if inspect.isawaitable(value):
        return await value
    return value


def _ensure_json_ready(value: Any) -> Any:
    """Приводит значение к JSON-совместимому виду."""

    if value is None or isinstance(value, (str, int, float, bool)):
        return value

    if isinstance(value, set):
        return [_ensure_json_ready(item) for item in sorted(value, key=lambda x: str(x))]

    if isinstance(value, (list, tuple)):
        return [_ensure_json_ready(item) for item in value]

    if isinstance(value, Mapping):
        return {str(key): _ensure_json_ready(val) for key, val in value.items()}

    if hasattr(value, "model_dump"):
        try:
            return value.model_dump(by_alias=True, mode="json")
        except TypeError:
            return _ensure_json_ready(value.model_dump())

    if hasattr(value, "model_dump_json"):
        try:
            return json.loads(value.model_dump_json())
        except Exception:  # pragma: no cover - защитный путь
            return str(value)

    try:
        json.dumps(value)
    except TypeError:
        return str(value)
    return value


def _component_meta(component: Any) -> Optional[dict]:
    """Возвращает метаинформацию FastMCP-компонента в JSON-совместимом виде."""

    get_meta = getattr(component, "get_meta", None)
    if callable(get_meta):
        try:
            meta = get_meta(include_fastmcp_meta=True)
        except TypeError:  # pragma: no cover - устаревшие сигнатуры
            meta = get_meta()
        except Exception:  # pragma: no cover - защитный путь
            meta = None
        if meta is not None:
            return _ensure_json_ready(meta)

    base_meta: dict = {}
    raw_meta = getattr(component, "meta", None)
    if isinstance(raw_meta, Mapping):
        base_meta.update(_ensure_json_ready(raw_meta))
    elif raw_meta is not None:
        base_meta.update(_ensure_json_ready(raw_meta))  # pragma: no cover - редкий случай

    tags = getattr(component, "tags", None)
    tag_list = [str(tag) for tag in sorted(tags, key=str)] if tags else []

    existing_fastmcp = base_meta.get("_fastmcp")
    if isinstance(existing_fastmcp, Mapping):
        fastmcp_meta = dict(existing_fastmcp)
    else:
        fastmcp_meta = {}
    fastmcp_meta["tags"] = tag_list
    base_meta["_fastmcp"] = fastmcp_meta
    return base_meta


def _component_to_manifest(component: Any, method_name: str, fallback_converter):
    """Преобразует компонент FastMCP в словарь для манифеста."""

    convert = getattr(component, method_name, None)
    if callable(convert):
        try:
            result = convert(include_fastmcp_meta=True)
        except TypeError:  # pragma: no cover - сигнатура без параметров
            result = convert()
        except Exception:  # pragma: no cover - защитный путь
            result = None
        if result is not None and hasattr(result, "model_dump"):
            try:
                return result.model_dump(by_alias=True, mode="json")
            except Exception:  # pragma: no cover - защитный путь
                pass

    try:
        return fallback_converter(component)
    except Exception:  # pragma: no cover - защитный путь
        return None


def _manual_tool_manifest(tool: Any) -> dict:
    return {
        "name": getattr(tool, "name", None),
        "title": getattr(tool, "title", None),
        "description": getattr(tool, "description", None),
        "inputSchema": _ensure_json_ready(getattr(tool, "parameters", None)),
        "outputSchema": _ensure_json_ready(getattr(tool, "output_schema", None)),
        "annotations": _ensure_json_ready(getattr(tool, "annotations", None)),
        "_meta": _component_meta(tool),
    }


def _manual_resource_manifest(resource: Any) -> dict:
    return {
        "name": getattr(resource, "name", None),
        "title": getattr(resource, "title", None),
        "uri": str(getattr(resource, "uri", ""))
        if getattr(resource, "uri", None) is not None
        else None,
        "description": getattr(resource, "description", None),
        "mimeType": getattr(resource, "mime_type", None),
        "size": getattr(resource, "size", None),
        "annotations": _ensure_json_ready(getattr(resource, "annotations", None)),
        "_meta": _component_meta(resource),
    }


def _manual_resource_template_manifest(template: Any) -> dict:
    return {
        "name": getattr(template, "name", None),
        "title": getattr(template, "title", None),
        "uriTemplate": str(getattr(template, "uri_template", ""))
        if getattr(template, "uri_template", None) is not None
        else None,
        "description": getattr(template, "description", None),
        "mimeType": getattr(template, "mime_type", None),
        "annotations": _ensure_json_ready(getattr(template, "annotations", None)),
        "_meta": _component_meta(template),
    }


def _manual_prompt_manifest(prompt: Any) -> dict:
    arguments = getattr(prompt, "arguments", None) or []
    return {
        "name": getattr(prompt, "name", None),
        "title": getattr(prompt, "title", None),
        "description": getattr(prompt, "description", None),
        "arguments": _ensure_json_ready(arguments),
        "_meta": _component_meta(prompt),
    }


async def _list_manager_items(manager_name: str, list_method: str) -> List[Any]:
    manager = getattr(app, manager_name, None)
    if manager is None:
        return []

    method = getattr(manager, list_method, None)
    if method is None:
        return []

    try:
        result = method()
        result = await _ensure_awaitable(result)
        if result is None:
            return []
        return list(result)
    except Exception:  # pragma: no cover - защитный путь
        return []


async def _collect_manifest_components() -> Tuple[List[dict], List[dict], List[dict], List[dict]]:
    tools: List[dict] = []
    resources: List[dict] = []
    prompts: List[dict] = []
    resource_templates: List[dict] = []

    for tool in await _list_manager_items("_tool_manager", "list_tools"):
        entry = _component_to_manifest(tool, "to_mcp_tool", _manual_tool_manifest)
        if entry is not None:
            tools.append(entry)

    for resource in await _list_manager_items("_resource_manager", "list_resources"):
        entry = _component_to_manifest(resource, "to_mcp_resource", _manual_resource_manifest)
        if entry is not None:
            resources.append(entry)

    for template in await _list_manager_items("_resource_manager", "list_resource_templates"):
        entry = _component_to_manifest(template, "to_mcp_template", _manual_resource_template_manifest)
        if entry is not None:
            resource_templates.append(entry)

    for prompt in await _list_manager_items("_prompt_manager", "list_prompts"):
        entry = _component_to_manifest(prompt, "to_mcp_prompt", _manual_prompt_manifest)
        if entry is not None:
            prompts.append(entry)

    return tools, resources, prompts, resource_templates


def _ensure_search_capability(manifest: dict) -> dict:
    capabilities = dict(manifest.get("capabilities", {}))
    existing_search = capabilities.get("search")
    if isinstance(existing_search, Mapping):
        updated_search = dict(existing_search)
    else:
        updated_search = {}

    if config.SEARCH_API_URL:
        updated_search["enabled"] = True
        updated_search.pop("reason", None)
    else:
        updated_search["enabled"] = False
        updated_search["reason"] = "SEARCH_API_URL is not configured"
    capabilities["search"] = updated_search
    manifest["capabilities"] = capabilities
    return manifest


def _normalize_manifest(manifest: dict) -> dict:
    """Приводит ответ fastmcp к структуре, ожидаемой спецификацией MCP."""

    if "mcp" in manifest and "server" in manifest:
        normalized = dict(manifest)
        env_section = dict(normalized.get("environment", {}))
        env_section.update(config.ENVIRONMENT_INFO)
        normalized["environment"] = env_section
        return _ensure_search_capability(normalized)

    environment = dict(manifest.get("environment", {}))
    environment.update(config.ENVIRONMENT_INFO)
    server_info = manifest.get("serverInfo", {})

    normalized: dict = {
        "mcp": {
            "version": environment.get("mcp")
            or environment.get("protocol")
            or "0.1.0"
        },
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


async def _build_manifest() -> dict:
    """Собирает MCP-манифест, используя fastmcp или запасную реализацию."""

    if _format_mcp_info is not None:
        manifest = _format_mcp_info(app)
        manifest = await _ensure_awaitable(manifest)
        if isinstance(manifest, (bytes, bytearray)):
            manifest = manifest.decode("utf-8")
        if isinstance(manifest, str):
            manifest = json.loads(manifest)
        return _normalize_manifest(manifest)

    tools, resources, prompts, resource_templates = await _collect_manifest_components()

    return _normalize_manifest(
        {
            "mcp": {"version": "0.1.0"},
            "server": {"name": getattr(app, "name", "anki-mcp")},
            "tools": tools,
            "resources": resources,
            "prompts": prompts,
            "resourceTemplates": resource_templates,
        }
    )


async def _manifest_response() -> JSONResponse:
    manifest = await _build_manifest()
    return JSONResponse(manifest, media_type="application/json")


@app.custom_route("/", methods=["GET"])
async def read_root(request: Request):  # pragma: no cover - тривиальный враппер
    return await _manifest_response()


@app.custom_route("/.well-known/mcp.json", methods=["GET"])
async def read_well_known_manifest(request: Request):  # pragma: no cover - тривиальный враппер
    return await _manifest_response()


__all__ = [
    "_format_mcp_info",
    "_build_manifest",
    "_normalize_manifest",
    "_manifest_response",
    "read_root",
    "read_well_known_manifest",
]
