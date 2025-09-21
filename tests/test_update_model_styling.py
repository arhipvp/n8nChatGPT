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

from anki_mcp import UpdateModelStylingArgs  # noqa: E402
from anki_mcp.tools.models import update_model_styling  # noqa: E402


def _unwrap(tool):
    return getattr(tool, "fn", tool)


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_update_model_styling_payload(monkeypatch):
    captured = {}

    async def fake_anki_call(action, params):
        captured["action"] = action
        captured["params"] = params
        return {"updated": True}

    monkeypatch.setattr("anki_mcp.services.client.anki_call", fake_anki_call)

    args = UpdateModelStylingArgs(
        model_name="Поля для ChatGPT",
        css=".card { color: #333; }",
    )

    result = await _unwrap(update_model_styling)(args)

    assert captured["action"] == "updateModelStyling"
    assert captured["params"] == {
        "model": {
            "name": "Поля для ChatGPT",
            "styling": {"css": ".card { color: #333; }"},
        }
    }
    assert result == {"updated": True}


@pytest.mark.anyio
async def test_update_model_styling_accepts_mappings(monkeypatch):
    captured = {}

    async def fake_anki_call(action, params):
        captured["action"] = action
        captured["params"] = params
        return None

    monkeypatch.setattr("anki_mcp.services.client.anki_call", fake_anki_call)

    payload = {"modelName": "Custom QA", "css": None}

    result = await _unwrap(update_model_styling)(payload)

    assert captured["action"] == "updateModelStyling"
    assert captured["params"] == {
        "model": {
            "name": "Custom QA",
            "styling": {"css": ""},
        }
    }
    assert result is None


@pytest.mark.anyio
async def test_update_model_styling_rejects_invalid_input(monkeypatch):
    async def fake_anki_call(action, params):  # pragma: no cover - should not run
        raise AssertionError("anki_call must not be invoked on invalid input")

    monkeypatch.setattr("anki_mcp.services.client.anki_call", fake_anki_call)

    with pytest.raises(ValueError) as exc:
        await _unwrap(update_model_styling)({"model_name": "  ", "css": "body {}"})

    assert "model_name" in str(exc.value)
