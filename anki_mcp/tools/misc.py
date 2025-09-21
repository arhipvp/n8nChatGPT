"""Прочие инструменты."""

from __future__ import annotations

from .. import app


@app.tool()
def greet(name: str) -> str:
    return f"Привет, {name}! Я твой MCP-сервер."


__all__ = ["greet"]
