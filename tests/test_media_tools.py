import base64
import sys
import types
from pathlib import Path

import pytest


try:  # pragma: no cover - используется только при отсутствии зависимости
    import fastmcp as _fastmcp_mod  # type: ignore  # noqa: F401
except ModuleNotFoundError:  # pragma: no cover - минимальные заглушки для тестовой среды
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

        def custom_route(self, *args, **kwargs):  # pragma: no cover - не используется здесь
            return self.tool(*args, **kwargs)

        def http_app(self):  # pragma: no cover - для совместимости с другими тестами
            async def _app(scope, receive, send):
                raise RuntimeError("HTTP app недоступно в тестовом окружении")

            return _app

    sys.modules.setdefault("fastmcp", types.ModuleType("fastmcp")).FastMCP = _FakeFastMCP


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server import DeleteMediaArgs, MediaRequest, delete_media, get_media  # noqa: E402


def _unwrap(tool):
    return getattr(tool, "fn", tool)


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_get_media_returns_payload(monkeypatch):
    payload = base64.b64encode(b"binary-data").decode("ascii")

    async def fake_anki_call(action, params):
        assert action == "retrieveMediaFile"
        assert params == {"filename": "sound.wav"}
        return payload

    monkeypatch.setattr("anki_mcp.services.anki.anki_call", fake_anki_call)

    args = MediaRequest(filename="sound.wav")
    result = await _unwrap(get_media)(args)

    assert result.filename == "sound.wav"
    assert result.data_base64 == payload
    assert result.size_bytes == len(b"binary-data")


@pytest.mark.anyio
async def test_get_media_raises_file_not_found(monkeypatch):
    async def fake_anki_call(action, params):
        raise RuntimeError("Media file not found")

    monkeypatch.setattr("anki_mcp.services.anki.anki_call", fake_anki_call)

    with pytest.raises(FileNotFoundError):
        await _unwrap(get_media)(MediaRequest(filename="missing.png"))


@pytest.mark.anyio
async def test_delete_media_reports_status(monkeypatch):
    async def fake_anki_call(action, params):
        assert action == "deleteMediaFile"
        assert params == {"filename": "audio/hello.mp3"}
        return None

    monkeypatch.setattr("anki_mcp.services.anki.anki_call", fake_anki_call)

    result = await _unwrap(delete_media)(DeleteMediaArgs(filename="audio/hello.mp3"))

    assert result == {
        "filename": "audio/hello.mp3",
        "deleted": True,
        "anki_response": None,
    }


@pytest.mark.anyio
async def test_delete_media_handles_partial_failures(monkeypatch):
    async def fake_anki_call(action, params):
        assert action == "deleteMediaFile"
        assert params == {"filename": "batch.bin"}
        return [True, False, None]

    monkeypatch.setattr("anki_mcp.services.anki.anki_call", fake_anki_call)

    result = await _unwrap(delete_media)(DeleteMediaArgs(filename="batch.bin"))

    assert result["filename"] == "batch.bin"
    assert result["anki_response"] == [True, False, None]
    assert result["deleted"] is False


@pytest.mark.anyio
async def test_delete_media_raises_file_not_found(monkeypatch):
    async def fake_anki_call(action, params):
        raise RuntimeError("No such file or directory")

    monkeypatch.setattr("anki_mcp.services.anki.anki_call", fake_anki_call)

    with pytest.raises(FileNotFoundError):
        await _unwrap(delete_media)(DeleteMediaArgs(filename="ghost.jpg"))
