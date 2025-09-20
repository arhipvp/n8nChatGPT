import importlib
import os

import pytest

import server


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _restore_env(original_deck, original_model):
    if original_deck is None:
        os.environ.pop("ANKI_DEFAULT_DECK", None)
    else:
        os.environ["ANKI_DEFAULT_DECK"] = original_deck

    if original_model is None:
        os.environ.pop("ANKI_DEFAULT_MODEL", None)
    else:
        os.environ["ANKI_DEFAULT_MODEL"] = original_model


def test_env_defaults_fallback_when_blank():
    original_deck = os.environ.get("ANKI_DEFAULT_DECK")
    original_model = os.environ.get("ANKI_DEFAULT_MODEL")

    try:
        os.environ["ANKI_DEFAULT_DECK"] = ""
        os.environ["ANKI_DEFAULT_MODEL"] = "   "
        module = importlib.reload(server)

        assert module.DEFAULT_DECK == "Default"
        assert module.DEFAULT_MODEL == "Basic"
    finally:
        _restore_env(original_deck, original_model)
        importlib.reload(server)


@pytest.mark.anyio
async def test_manifest_environment_contains_defaults():
    original_deck = os.environ.get("ANKI_DEFAULT_DECK")
    original_model = os.environ.get("ANKI_DEFAULT_MODEL")

    try:
        os.environ["ANKI_DEFAULT_DECK"] = "DeckFromEnv"
        os.environ["ANKI_DEFAULT_MODEL"] = "ModelFromEnv"
        module = importlib.reload(server)

        # Сбросим форматтер fastmcp, чтобы гарантированно использовать нормализацию.
        module._format_mcp_info = None

        manifest = await module._build_manifest()
        assert manifest["environment"]["defaultDeck"] == "DeckFromEnv"
        assert manifest["environment"]["defaultModel"] == "ModelFromEnv"
    finally:
        _restore_env(original_deck, original_model)
        importlib.reload(server)
