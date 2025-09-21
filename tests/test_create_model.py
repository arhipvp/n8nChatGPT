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
    CreateModelArgs,
    create_model,
)


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _unwrap(tool):
    return getattr(tool, "fn", tool)


@pytest.mark.anyio
async def test_create_model_payload(monkeypatch):
    captured = {}

    async def fake_anki_call(action, params):
        captured["action"] = action
        captured["params"] = params
        return {"created": True}

    monkeypatch.setattr("anki_mcp.services.client.anki_call", fake_anki_call)

    args = CreateModelArgs(
        model_name="Custom QA",
        in_order_fields=["Question", "Answer", "Context"],
        card_templates=[
            CardTemplateSpec(
                name="Card 1",
                front="<div class=\"question\">{{Question}}</div>",
                back="{{FrontSide}}\n<hr id=\"answer\">\n<div class=\"answer\">{{Answer}}</div>",
            )
        ],
        css=".card { font-family: Inter; }",
        is_cloze=False,
        options={"latexPre": "\\documentclass{article}"},
    )

    result = await _unwrap(create_model)(args)

    assert captured["action"] == "createModel"
    assert captured["params"]["modelName"] == "Custom QA"
    assert captured["params"]["inOrderFields"] == [
        "Question",
        "Answer",
        "Context",
    ]
    assert captured["params"]["cardTemplates"] == [
        {
            "Name": "Card 1",
            "Front": "<div class=\"question\">{{Question}}</div>",
            "Back": "{{FrontSide}}\n<hr id=\"answer\">\n<div class=\"answer\">{{Answer}}</div>",
        }
    ]
    assert captured["params"]["css"] == ".card { font-family: Inter; }"
    assert captured["params"]["isCloze"] is False
    assert captured["params"]["latexPre"] == "\\documentclass{article}"

    assert result.model_name == "Custom QA"
    assert result.in_order_fields == ["Question", "Answer", "Context"]
    assert result.options == {
        "latexPre": "\\documentclass{article}",
        "isCloze": False,
    }
    assert result.anki_response == {"created": True}


@pytest.mark.anyio
async def test_create_model_rejects_reserved_option(monkeypatch):
    async def fake_anki_call(action, params):  # pragma: no cover - should not be called
        raise AssertionError("anki_call must not be invoked on invalid input")

    monkeypatch.setattr("anki_mcp.services.client.anki_call", fake_anki_call)

    with pytest.raises(ValueError) as exc:
        await _unwrap(create_model)(
            {
                "modelName": "Test",
                "inOrderFields": ["Front"],
                "cardTemplates": [{"Name": "Card 1", "Front": "{{Front}}", "Back": "{{Front}}"}],
                "options": {"css": "body {}"},
            }
        )

    assert "options cannot override reserved parameter" in str(exc.value)


@pytest.mark.anyio
async def test_create_model_conflicting_is_cloze(monkeypatch):
    async def fake_anki_call(action, params):  # pragma: no cover - should not run
        raise AssertionError("anki_call should not be used when validation fails")

    monkeypatch.setattr("anki_mcp.services.client.anki_call", fake_anki_call)

    with pytest.raises(ValueError) as exc:
        await _unwrap(create_model)(
            CreateModelArgs(
                model_name="Cloze", 
                in_order_fields=["Text"],
                card_templates=[
                    CardTemplateSpec(name="Cloze", front="{{cloze:Text}}", back="{{cloze:Text}}")
                ],
                is_cloze=False,
                options={"isCloze": True},
            )
        )

    assert "is_cloze conflicts" in str(exc.value)
