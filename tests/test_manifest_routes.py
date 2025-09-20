import pytest
from fastapi.testclient import TestClient

pytest.importorskip("fastmcp")

import server


@pytest.fixture(scope="module")
def client():
    return TestClient(server.app.http_app())


@pytest.mark.parametrize("path", ["/", "/.well-known/mcp.json"])
def test_manifest_endpoints_return_manifest_json(client, path):
    response = client.get(path)

    assert response.status_code == 200
    assert response.headers.get("content-type", "").startswith("application/json")

    payload = response.json()
    for key in ("mcp", "server", "tools"):
        assert key in payload
