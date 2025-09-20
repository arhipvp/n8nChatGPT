import pytest

pytest.importorskip("fastmcp")

import server


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_search_action_returns_normalized_response(monkeypatch):
    monkeypatch.setattr(server, "SEARCH_API_URL", "https://example.com/search")
    monkeypatch.setattr(server, "SEARCH_API_KEY", "secret-token")

    captured = {}

    class DummyResponse:
        def __init__(self) -> None:
            self._json = {
                "results": [
                    {
                        "title": "Example",
                        "url": "https://example.com",
                        "snippet": "Hello",
                        "score": 0.9,
                    }
                ],
                "nextCursor": "token-123",
            }

        def raise_for_status(self) -> None:
            captured["raise_called"] = True

        def json(self):
            return self._json

    class DummyClient:
        def __init__(self, *args, **kwargs) -> None:
            captured["client_kwargs"] = kwargs

        async def __aenter__(self):
            captured["entered"] = True
            return self

        async def __aexit__(self, exc_type, exc, tb):
            captured["exited"] = True
            return False

        async def post(self, url, json=None, headers=None):
            captured["request"] = {"url": url, "json": json, "headers": headers}
            return DummyResponse()

    monkeypatch.setattr(server.httpx, "AsyncClient", DummyClient)

    request = server.SearchRequest(query="  python  ", limit=5, cursor="cursor-1")
    response = await server.search.fn(request)

    assert isinstance(response, server.SearchResponse)
    assert response.results and response.results[0].title == "Example"
    assert str(response.results[0].url).startswith("https://example.com")
    assert response.next_cursor == "token-123"

    if hasattr(response, "model_dump"):
        dumped = response.model_dump(by_alias=True)
    else:  # pragma: no cover - pydantic v1 fallback
        dumped = response.dict(by_alias=True)
    assert dumped["nextCursor"] == "token-123"

    expected_payload = {
        "query": "python",
        "limit": 5,
        "cursor": "cursor-1",
    }
    assert captured["request"] == {
        "url": "https://example.com/search",
        "json": expected_payload,
        "headers": {"Authorization": "Bearer secret-token"},
    }
    assert captured["client_kwargs"].get("timeout") == 15.0
    assert captured.get("raise_called") is True
    assert captured.get("entered") and captured.get("exited")
