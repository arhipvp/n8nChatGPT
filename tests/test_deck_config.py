import asyncio

import pytest

import test_deck_tools as deck_helpers

from server import (
    DeckConfig,
    GetDeckConfigArgs,
    SaveDeckConfigArgs,
    get_deck_config,
    save_deck_config,
)


SAMPLE_DECK_CONFIG_RAW = {
    "id": 42,
    "name": "Custom",
    "autoplay": True,
    "replayq": False,
    "maxTaken": 75,
    "new": {
        "perDay": 25,
        "delays": [1.0, 10.0],
        "ints": [1, 4, 7],
        "initialFactor": 2500,
        "order": 1,
        "bury": True,
        "separate": True,
    },
    "rev": {
        "perDay": 200,
        "ease4": 1.3,
        "hardFactor": 1.2,
        "ivlFct": 1.0,
        "maxIvl": 36500,
        "minSpace": 1,
        "bury": True,
        "seed": 0,
    },
    "lapse": {
        "delays": [10.0],
        "leechAction": 0,
        "leechFails": 8,
        "minInt": 1,
        "mult": 0.0,
    },
}


def _model_dump(instance):
    if hasattr(instance, "model_dump"):
        return instance.model_dump(by_alias=True, exclude_none=True)
    return instance.dict(by_alias=True, exclude_none=True)


def test_get_deck_config_payload(monkeypatch):
    calls = []

    async def fake_anki_call(action, params):
        calls.append((action, params))
        assert action == "getDeckConfig"
        assert params == {"deck": "Default"}
        return SAMPLE_DECK_CONFIG_RAW

    monkeypatch.setattr("anki_mcp.services.client.anki_call", fake_anki_call)

    get_deck_config_fn = deck_helpers._unwrap_tool(get_deck_config)
    args = GetDeckConfigArgs(deck="Default")
    result = asyncio.run(get_deck_config_fn(args))

    assert isinstance(result, DeckConfig)
    assert result.name == "Custom"
    assert result.new.per_day == 25
    assert result.rev.interval_factor == pytest.approx(1.0)
    assert result.lapse.leech_fails == 8
    assert calls == [("getDeckConfig", {"deck": "Default"})]


def test_get_deck_config_invalid_response(monkeypatch):
    async def fake_anki_call(action, params):
        assert action == "getDeckConfig"
        return "not-a-mapping"

    monkeypatch.setattr("anki_mcp.services.client.anki_call", fake_anki_call)

    get_deck_config_fn = deck_helpers._unwrap_tool(get_deck_config)

    with pytest.raises(ValueError) as excinfo:
        asyncio.run(get_deck_config_fn({"deck": "Default"}))

    assert "Invalid getDeckConfig response" in str(excinfo.value)


def test_save_deck_config_updates_and_assigns(monkeypatch):
    calls = []
    config = DeckConfig(**SAMPLE_DECK_CONFIG_RAW)
    expected_payload = _model_dump(config)

    async def fake_anki_call(action, params):
        calls.append((action, params))
        if action == "saveDeckConfig":
            assert params == {"config": expected_payload}
            return None
        if action == "setDeckConfigId":
            assert params == {"deck": "Inbox", "configId": 42}
            return {"applied": True}
        raise AssertionError(f"unexpected action {action}")

    monkeypatch.setattr("anki_mcp.services.client.anki_call", fake_anki_call)

    save_deck_config_fn = deck_helpers._unwrap_tool(save_deck_config)
    args = SaveDeckConfigArgs(config=config, deck="Inbox")
    result = asyncio.run(save_deck_config_fn(args))

    assert result == {
        "save_result": None,
        "configId": 42,
        "deck": "Inbox",
        "set_result": {"applied": True},
    }
    assert calls == [
        ("saveDeckConfig", {"config": expected_payload}),
        ("setDeckConfigId", {"deck": "Inbox", "configId": 42}),
    ]


def test_save_deck_config_requires_id_for_assignment(monkeypatch):
    calls = []
    raw_without_id = {key: value for key, value in SAMPLE_DECK_CONFIG_RAW.items() if key != "id"}
    config = DeckConfig(**raw_without_id)

    async def fake_anki_call(action, params):
        calls.append((action, params))
        assert action == "saveDeckConfig"
        return None

    monkeypatch.setattr("anki_mcp.services.client.anki_call", fake_anki_call)

    save_deck_config_fn = deck_helpers._unwrap_tool(save_deck_config)

    with pytest.raises(ValueError) as excinfo:
        asyncio.run(save_deck_config_fn(SaveDeckConfigArgs(config=config, deck="Inbox")))

    assert "must include id" in str(excinfo.value)
    assert calls == [("saveDeckConfig", {"config": _model_dump(config)})]


def test_save_deck_config_validation_error(monkeypatch):
    async def forbidden_call(action, params):
        raise AssertionError("anki_call should not be invoked on validation errors")

    monkeypatch.setattr("anki_mcp.services.client.anki_call", forbidden_call)

    save_deck_config_fn = deck_helpers._unwrap_tool(save_deck_config)

    with pytest.raises(ValueError) as excinfo:
        asyncio.run(save_deck_config_fn({"deck": " ", "config": {}}))

    assert "Invalid save_deck_config arguments" in str(excinfo.value)
