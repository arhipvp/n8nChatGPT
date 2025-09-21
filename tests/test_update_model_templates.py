import sys
import types
from pathlib import Path

import pytest

try:  # pragma: no cover - exercised only when dependency missing
    import fastmcp as _fastmcp_mod  # type: ignore  # noqa: F401
except ModuleNotFoundError:  # pragma: no cover - executed in minimal test environments
    class _FakeToolWrapper:
        def __init__(self, func):
            self.fn = func

        def __call__(self, *args, **kwargs):
            return self.fn(*args, **kwargs)

    class _FakeFastMCP:
        def __init__(self, *args, **kwargs):
            pass

        def tool(self, *args, **kwargs):
            def decorator(func):
                return _FakeToolWrapper(func)

            return decorator

        def custom_route(self, *args, **kwargs):
            return self.tool(*args, **kwargs)

        def http_app(self):  # pragma: no cover - not used here
            async def _app(scope, receive, send):
                raise RuntimeError("HTTP app is not available in tests")

            return _app

    sys.modules.setdefault("fastmcp", types.ModuleType("fastmcp")).FastMCP = _FakeFastMCP


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server import (  # noqa: E402
    CardTemplateSpec,
    UpdateModelTemplatesArgs,
    update_model_templates,
)


def _unwrap(tool):
    return getattr(tool, "fn", tool)


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_update_model_templates_payload(monkeypatch):
    captured = {}

    async def fake_anki_call(action, params):
        captured["action"] = action
        captured["params"] = params
        return {"updated": True}

    monkeypatch.setattr("anki_mcp.services.client.anki_call", fake_anki_call)

    args = UpdateModelTemplatesArgs(
        model_name="Поля для ChatGPT",
        templates={
            "Card 1": CardTemplateSpec(
                name="Card 1",
                front="<div>{{Prompt}}</div>",
                back="{{FrontSide}}\n<hr>\n<div>{{Response}}</div>",
            )
        },
    )

    result = await _unwrap(update_model_templates)(args)

    assert captured["action"] == "updateModelTemplates"
    assert captured["params"] == {
        "model": {
            "name": "Поля для ChatGPT",
            "templates": {
                "Card 1": {
                    "Front": "<div>{{Prompt}}</div>",
                    "Back": "{{FrontSide}}\n<hr>\n<div>{{Response}}</div>",
                }
            },
        }
    }
    assert result == {"updated": True}


@pytest.mark.anyio
async def test_update_model_templates_rejects_mismatched_names(monkeypatch):
    async def fake_anki_call(action, params):  # pragma: no cover - should not run
        raise AssertionError("anki_call must not be invoked on invalid input")

    monkeypatch.setattr("anki_mcp.services.client.anki_call", fake_anki_call)

    args = UpdateModelTemplatesArgs(
        model_name="Поля для ChatGPT",
        templates={
            "Card 1": CardTemplateSpec(
                name="Card 2",
                front="<div>Q</div>",
                back="<div>A</div>",
            )
        },
    )

    with pytest.raises(ValueError) as exc:
        await _unwrap(update_model_templates)(args)

    assert "must match template name" in str(exc.value)


@pytest.mark.anyio
async def test_update_model_templates_accepts_mappings(monkeypatch):
    captured = {}

    async def fake_anki_call(action, params):
        captured["action"] = action
        captured["params"] = params
        return None

    monkeypatch.setattr("anki_mcp.services.client.anki_call", fake_anki_call)

    payload = {
        "modelName": "Custom QA",
        "templates": {
            "Card 1": {
                "Front": "<div>{{Question}}</div>",
                "Back": "{{FrontSide}}\n<hr>\n<div>{{Answer}}</div>",
                "Name": "Card 1",
            }
        },
    }

    result = await _unwrap(update_model_templates)(payload)

    assert captured["action"] == "updateModelTemplates"
    assert captured["params"] == {
        "model": {
            "name": "Custom QA",
            "templates": {
                "Card 1": {
                    "Front": "<div>{{Question}}</div>",
                    "Back": "{{FrontSide}}\n<hr>\n<div>{{Answer}}</div>",
                }
            },
        }
    }
    assert result is None


@pytest.mark.anyio
async def test_update_model_templates_accepts_model_info_payload(monkeypatch):
    captured = {}

    async def fake_anki_call(action, params):
        captured["action"] = action
        captured["params"] = params
        return {"ok": True}

    monkeypatch.setattr("anki_mcp.services.client.anki_call", fake_anki_call)

    payload = {
        "modelName": "Custom QA",
        "templates": {
            "Card 1": {
                "Front": "<div>{{Question}}</div>",
                "Back": "{{FrontSide}}\n<hr>\n<div>{{Answer}}</div>",
            }
        },
    }

    result = await _unwrap(update_model_templates)(payload)

    assert captured["action"] == "updateModelTemplates"
    assert captured["params"] == {
        "model": {
            "name": "Custom QA",
            "templates": {
                "Card 1": {
                    "Front": "<div>{{Question}}</div>",
                    "Back": "{{FrontSide}}\n<hr>\n<div>{{Answer}}</div>",
                }
            },
        }
    }
    assert result == {"ok": True}


@pytest.mark.anyio
async def test_update_model_templates_rejects_conflicting_name(monkeypatch):
    async def fake_anki_call(action, params):  # pragma: no cover - should not run
        raise AssertionError("anki_call must not be invoked on invalid input")

    monkeypatch.setattr("anki_mcp.services.client.anki_call", fake_anki_call)

    payload = {
        "modelName": "Custom QA",
        "templates": {
            "Card 1": {
                "Name": "Card 2",
                "Front": "<div>{{Question}}</div>",
                "Back": "{{FrontSide}}\n<hr>\n<div>{{Answer}}</div>",
            }
        },
    }

    with pytest.raises(ValueError) as exc:
        await _unwrap(update_model_templates)(payload)

    assert "must match template name" in str(exc.value)
