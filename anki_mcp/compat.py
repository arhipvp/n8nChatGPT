"""Совместимость с различными зависимостями и версиями библиотек."""

from __future__ import annotations

import json
from typing import Any, Dict, Optional, Type, TypeVar


try:  # pragma: no cover - предпочитаем FastAPI при наличии
    from fastapi import Request  # type: ignore
    from fastapi.responses import JSONResponse  # type: ignore
except Exception:  # pragma: no cover - fallback, если FastAPI недоступен
    try:  # pragma: no cover - запасной вариант на Starlette
        from starlette.requests import Request  # type: ignore
    except Exception:  # pragma: no cover - минимальный заглушечный Request
        class Request:  # type: ignore[too-many-ancestors]
            """Минимальная заглушка, используемая в деградированном окружении."""

            pass

    try:  # pragma: no cover - Starlette может быть доступна даже без FastAPI
        from starlette.responses import JSONResponse  # type: ignore
    except Exception:  # pragma: no cover - последняя линия обороны
        class JSONResponse:  # type: ignore[too-many-ancestors]
            """Простейшая реализация JSONResponse для ASGI."""

            def __init__(
                self,
                content,
                media_type: str = "application/json",
                status_code: int = 200,
                headers: Optional[Dict[str, str]] = None,
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

            async def __call__(self, scope, receive, send):  # pragma: no cover - ASGI fallback
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


try:  # pragma: no cover - поддержка Pydantic v2
    from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, constr
except ImportError:  # pragma: no cover - Pydantic v1 без ConfigDict
    from pydantic import AnyHttpUrl, BaseModel, Field, constr  # type: ignore

    ConfigDict = None  # type: ignore[assignment]


try:  # pragma: no cover - валидаторы доступны не во всех версиях
    from pydantic import field_validator, model_validator, root_validator, validator  # type: ignore
except ImportError:  # pragma: no cover - Pydantic v1
    try:  # pragma: no cover - Pydantic v1 предоставляет validator/root_validator
        from pydantic import root_validator, validator  # type: ignore
    except ImportError:  # pragma: no cover
        root_validator = None  # type: ignore[assignment]
        validator = None  # type: ignore[assignment]

    model_validator = None  # type: ignore[assignment]
    try:
        from pydantic import field_validator  # type: ignore
    except ImportError:  # pragma: no cover
        field_validator = None  # type: ignore[assignment]


T_Model = TypeVar("T_Model", bound=BaseModel)


def model_validate(model: Type[T_Model], data: Any) -> T_Model:
    """Совместимая обёртка вокруг `model_validate`/`parse_obj`."""

    if hasattr(model, "model_validate"):
        return model.model_validate(data)  # type: ignore[attr-defined]
    return model.parse_obj(data)  # type: ignore[attr-defined]


__all__ = [
    "AnyHttpUrl",
    "BaseModel",
    "ConfigDict",
    "Field",
    "JSONResponse",
    "Request",
    "constr",
    "field_validator",
    "model_validate",
    "model_validator",
    "root_validator",
    "validator",
]
