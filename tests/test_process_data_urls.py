import base64
import hashlib
import sys
from pathlib import Path

import pytest

from _fastmcp_stub import ensure_stub_installed

ensure_stub_installed()

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import server


@pytest.mark.asyncio
async def test_process_data_url_with_newlines(monkeypatch):
    raw = b"test-image-bytes"
    b64 = base64.b64encode(raw).decode("ascii")
    # вставляем перевод строки в base64
    b64_with_newlines = b64[:5] + "\n" + b64[5:10] + "\n" + b64[10:]
    data_url = f"data:image/png;base64,{b64_with_newlines}"

    fields = {"Image": data_url}
    results: list[dict] = []

    stored = {}

    async def fake_store_media_file(filename: str, data_b64: str):
        stored["filename"] = filename
        stored["data"] = data_b64

    monkeypatch.setattr(server, "store_media_file", fake_store_media_file)

    await server.process_data_urls_in_fields(fields, results, note_index=0)

    digest = hashlib.sha1(raw).hexdigest()
    expected_fname = f"img_{digest}.png"

    assert fields["Image"] == expected_fname
    assert stored["filename"] == expected_fname
    assert stored["data"] == base64.b64encode(raw).decode("ascii")
    assert results == [{"index": 0, "info": f"data_url_saved:Image->{expected_fname}"}]
