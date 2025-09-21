import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from anki_mcp.services import client


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_anki_call_rejects_non_string_action():
    with pytest.raises(TypeError):
        await client.anki_call(123)  # type: ignore[arg-type]


@pytest.mark.anyio
async def test_store_media_file_delegates(monkeypatch):
    captured = {}

    async def fake_anki_call(action, params=None, *, version=6):
        captured["payload"] = (action, params, version)
        return {"ok": True}

    monkeypatch.setattr(client, "anki_call", fake_anki_call)

    result = await client.store_media_file("image.png", "ZGF0YQ==")

    assert result == {"ok": True}
    assert captured["payload"] == (
        "storeMediaFile",
        {"filename": "image.png", "data": "ZGF0YQ=="},
        6,
    )
