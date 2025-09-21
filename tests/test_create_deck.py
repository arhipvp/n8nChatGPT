import asyncio

import pytest

import test_deck_tools as deck_helpers

from server import CreateDeckArgs, create_deck


def test_create_deck_payload(monkeypatch):
    calls = []

    async def fake_anki_call(action, params):
        calls.append((action, params))
        assert action == "createDeck"
        assert params == {"deck": "Inbox"}
        return {"status": "ok"}

    monkeypatch.setattr("anki_mcp.services.client.anki_call", fake_anki_call)

    create_deck_fn = deck_helpers._unwrap_tool(create_deck)
    args = CreateDeckArgs(deck="Inbox")
    result = asyncio.run(create_deck_fn(args))

    assert result == {"status": "ok"}
    assert calls == [("createDeck", {"deck": "Inbox"})]


def test_create_deck_validation_error(monkeypatch):
    async def forbidden_call(action, params):
        raise AssertionError("anki_call should not be invoked on validation errors")

    monkeypatch.setattr("anki_mcp.services.client.anki_call", forbidden_call)

    create_deck_fn = deck_helpers._unwrap_tool(create_deck)

    with pytest.raises(ValueError) as excinfo:
        asyncio.run(create_deck_fn({"deck": ""}))

    assert "Invalid create_deck arguments" in str(excinfo.value)


def test_create_deck_propagates_anki_errors(monkeypatch):
    async def fake_anki_call(action, params):
        raise RuntimeError("boom")

    monkeypatch.setattr("anki_mcp.services.client.anki_call", fake_anki_call)

    create_deck_fn = deck_helpers._unwrap_tool(create_deck)

    with pytest.raises(RuntimeError):
        asyncio.run(create_deck_fn({"name": "Inbox"}))
