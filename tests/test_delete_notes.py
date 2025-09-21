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

        def custom_route(self, *args, **kwargs):  # pragma: no cover - unused in these tests
            return self.tool(*args, **kwargs)

        def http_app(self):  # pragma: no cover - exercised only in manifest tests elsewhere
            async def _app(scope, receive, send):
                raise RuntimeError("HTTP app is not available in tests")

            return _app

    sys.modules.setdefault("fastmcp", types.ModuleType("fastmcp")).FastMCP = _FakeFastMCP


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server import DeleteNotesArgs, delete_notes  # noqa: E402  # pylint: disable=wrong-import-position


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_delete_notes_calls_anki_and_handles_none(monkeypatch):
    calls = []

    async def fake_anki_call(action, params):
        calls.append((action, params))
        assert action == "deleteNotes"
        return None

    monkeypatch.setattr("anki_mcp.services.anki.anki_call", fake_anki_call)

    args = DeleteNotesArgs(noteIds=[1, 2, 3])
    delete_fn = getattr(delete_notes, "fn", delete_notes)
    result = await delete_fn(args)

    assert calls == [("deleteNotes", {"notes": [1, 2, 3]})]
    assert result.deleted == 3
    assert result.missing == 0


@pytest.mark.anyio
async def test_delete_notes_normalizes_list_response(monkeypatch):
    async def fake_anki_call(action, params):
        assert action == "deleteNotes"
        assert params == {"notes": [10, 20, 30, 40, 50]}
        return [True, False, None, {"status": "missing"}, {"status": "ok"}]

    monkeypatch.setattr("anki_mcp.services.anki.anki_call", fake_anki_call)

    args = DeleteNotesArgs(noteIds=[10, 20, 30, 40, 50])
    delete_fn = getattr(delete_notes, "fn", delete_notes)
    result = await delete_fn(args)

    assert result.deleted == 2
    assert result.missing == 3


@pytest.mark.anyio
async def test_delete_notes_handles_mapping_counts(monkeypatch):
    async def fake_anki_call(action, params):
        assert action == "deleteNotes"
        assert params == {"notes": [7, 8, 9, 10]}
        return {"deleted": 3, "missing": 1}

    monkeypatch.setattr("anki_mcp.services.anki.anki_call", fake_anki_call)

    args = DeleteNotesArgs(noteIds=[7, 8, 9, 10])
    delete_fn = getattr(delete_notes, "fn", delete_notes)
    result = await delete_fn(args)

    assert result.deleted == 3
    assert result.missing == 1


def test_delete_notes_args_require_note_ids():
    with pytest.raises(Exception) as exc_info:
        DeleteNotesArgs(noteIds=[])

    assert "noteIds" in str(exc_info.value)
