"""Инструменты общего назначения и синхронизации."""

from __future__ import annotations

from typing import Any, Dict, Mapping

from .. import app
from ..schemas import InvokeActionArgs
from ..services import client as anki_client


@app.tool(name="anki.invoke")
async def invoke_action(args: InvokeActionArgs) -> Any:
    params_payload: Dict[str, Any]
    if args.params is None:
        params_payload = {}
    elif isinstance(args.params, dict):
        params_payload = dict(args.params)
    elif isinstance(args.params, Mapping):
        params_payload = dict(args.params)
    else:
        raise TypeError("params must be a mapping of argument names to values")

    if args.version is None:
        version = 6
    elif isinstance(args.version, bool) or not isinstance(args.version, int):
        raise TypeError("version must be an integer")
    else:
        version = args.version

    payload = {
        "action": args.action,
        "version": version,
        "params": params_payload,
    }

    result = await anki_client.anki_call(
        payload["action"], payload["params"], version=payload["version"]
    )
    return result


_SYNC_VALUE_ERROR_KEYWORDS = (
    "invalid",
    "missing",
    "empty",
    "required",
    "unknown",
    "no such",
    "not found",
    "please provide",
    "must ",
    "should ",
)


@app.tool(name="anki.sync")
async def sync() -> Mapping[str, Any]:
    try:
        result = await anki_client.anki_call("sync", {})
    except RuntimeError as exc:
        detail = str(exc)
        if detail.lower().startswith("anki error:"):
            detail = detail.split(":", 1)[1].strip() or detail
        lowered = detail.lower()
        message = f"Не удалось выполнить синхронизацию Anki: {detail}"
        if any(keyword in lowered for keyword in _SYNC_VALUE_ERROR_KEYWORDS):
            raise ValueError(message) from exc
        raise RuntimeError(message) from exc

    if result is None:
        return {"synced": True}

    if isinstance(result, bool):
        return {"synced": bool(result)}

    if isinstance(result, Mapping):
        return dict(result)

    return {"result": result}


__all__ = ["invoke_action", "sync"]
