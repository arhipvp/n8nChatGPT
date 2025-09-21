import base64
import hashlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from anki_mcp.services import media


@pytest.fixture
def anyio_backend():
    return "asyncio"


def test_ensure_img_tag_adds_when_missing():
    result = media.ensure_img_tag("", "picture.png")
    assert "picture.png" in result
    assert result.count("picture.png") == 1


def test_auto_link_urls_skips_existing_anchor():
    text = 'см. <a href="https://example.com">https://example.com</a>'
    assert media.auto_link_urls(text) == text


def test_sanitize_image_payload_data_url():
    raw = base64.b64encode(b"payload").decode("ascii")
    clean, ext = media.sanitize_image_payload(f"data:image/png;base64,{raw}")
    assert clean == raw
    assert ext == "png"


@pytest.mark.anyio
async def test_process_data_urls_in_fields(monkeypatch):
    raw = b"image-bytes"
    payload = base64.b64encode(raw).decode("ascii")
    data_url = f"data:image/png;base64,{payload}"
    fields = {"Front": f"Question {data_url} text"}
    results: list[dict] = []

    saved = {}

    async def fake_store(filename, data):
        saved["filename"] = filename
        saved["data"] = data

    monkeypatch.setattr(media, "store_media_file", fake_store)

    await media.process_data_urls_in_fields(fields, results, 0)

    digest = hashlib.sha1(raw).hexdigest()
    expected_filename = f"img_{digest}.png"

    assert saved["filename"] == expected_filename
    assert saved["data"] == payload
    assert results == [
        {"index": 0, "info": f"data_url_saved:Front->{expected_filename}"}
    ]
    assert expected_filename in fields["Front"]
    assert "<img" in fields["Front"]


@pytest.mark.anyio
async def test_fetch_image_as_base64_rejects_small_max_side():
    with pytest.raises(ValueError):
        await media.fetch_image_as_base64("http://example.com", 0)
