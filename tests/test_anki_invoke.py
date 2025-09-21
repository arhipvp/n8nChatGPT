import sys
import types
from pathlib import Path

import pytest
from pydantic import ValidationError

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

from server import InvokeActionArgs, invoke_action  # noqa: E402


def _unwrap(tool):
    return getattr(tool, "fn", tool)


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_invoke_action_passes_payload(monkeypatch):
    payloads = []

    async def fake_anki_call(action, params, *, version):
        payloads.append({"action": action, "params": params, "version": version})
        return {"echo": len(payloads)}

    monkeypatch.setattr("anki_mcp.services.client.anki_call", fake_anki_call)

    first_args = InvokeActionArgs(action="multi", params={"actions": []}, version=7)
    first_result = await _unwrap(invoke_action)(first_args)

    second_args = InvokeActionArgs(action="deckNames")
    second_result = await _unwrap(invoke_action)(second_args)

    assert first_result == {"echo": 1}
    assert second_result == {"echo": 2}
    assert payloads == [
        {"action": "multi", "params": {"actions": []}, "version": 7},
        {"action": "deckNames", "params": {}, "version": 6},
    ]


def test_invoke_action_rejects_boolean_version():
    with pytest.raises((TypeError, ValidationError), match="version must be an integer"):
        InvokeActionArgs(action="deckNames", version=True)


def test_invoke_action_args_rejects_empty_action():
    with pytest.raises(ValidationError):
        InvokeActionArgs(action="   ")
