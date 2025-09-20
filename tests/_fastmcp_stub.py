import sys
import types
from typing import Iterable, Optional

try:  # pragma: no cover - используем FastAPI, если доступен
    from fastapi import FastAPI
except Exception:  # pragma: no cover - в деградированном окружении маршруты не нужны
    FastAPI = None  # type: ignore


class FakeFastMCP:
    """Минимальный стаб FastMCP для unit-тестов без зависимости от fastmcp."""

    def __init__(self, *args, **kwargs):
        self.name = args[0] if args else "anki-mcp"
        self._app = FastAPI() if FastAPI is not None else None

    def tool(self, *args, **kwargs):
        def decorator(func):
            return func

        return decorator

    def custom_route(self, path: str, methods: Optional[Iterable[str]] = None, *args, **kwargs):
        def decorator(func):
            if self._app is not None:
                route_methods = list(methods or ["GET"])
                self._app.add_api_route(path, func, methods=route_methods)
            return func

        return decorator

    def http_app(self):
        if self._app is None:
            raise AttributeError("http_app unavailable in stub")
        return self._app


def ensure_stub_installed():
    module = types.ModuleType("fastmcp")
    module.FastMCP = FakeFastMCP
    sys.modules["fastmcp"] = module


__all__ = ["ensure_stub_installed", "FakeFastMCP"]
