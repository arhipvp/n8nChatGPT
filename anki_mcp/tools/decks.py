"""Инструменты Anki, связанные с колодами."""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Union

from .. import app
from ..compat import model_validate
from ..schemas import (
    CreateDeckArgs,
    DeckConfig,
    DeckInfo,
    DeleteDecksArgs,
    GetDeckConfigArgs,
    ListDecksResponse,
    ListTagsResponse,
    RenameDeckArgs,
    SaveDeckConfigArgs,
)
from ..services import client as anki_client


def _model_dump(instance: Any, *, by_alias: bool = False, exclude_none: bool = False) -> Dict[str, Any]:
    if hasattr(instance, "model_dump"):
        return instance.model_dump(by_alias=by_alias, exclude_none=exclude_none)
    if hasattr(instance, "dict"):
        return instance.dict(by_alias=by_alias, exclude_none=exclude_none)
    raise TypeError("instance must be a Pydantic model")


@app.tool(name="anki.list_decks")
async def list_decks() -> List[DeckInfo]:
    raw_decks = await anki_client.anki_call("deckNamesAndIds", {})

    if raw_decks is None:
        return []

    if not isinstance(raw_decks, Mapping):
        raise ValueError("deckNamesAndIds response must be a mapping of deck names to ids")

    deck_infos: List[DeckInfo] = []
    for name, deck_id in raw_decks.items():
        if not isinstance(name, str):
            raise ValueError(f"deckNamesAndIds returned invalid deck name: {name!r}")

        if isinstance(deck_id, bool):
            raise ValueError(
                f"deckNamesAndIds returned non-integer deck id for {name!r}: {deck_id!r}"
            )

        try:
            normalized_id = int(deck_id)
        except (TypeError, ValueError):
            raise ValueError(
                f"deckNamesAndIds returned non-integer deck id for {name!r}: {deck_id!r}"
            ) from None

        deck_infos.append(DeckInfo(id=normalized_id, name=name))

    response = ListDecksResponse(decks=deck_infos)
    return response.decks


@app.tool(name="anki.list_tags")
async def list_tags() -> ListTagsResponse:
    try:
        raw_tags = await anki_client.anki_call("getTags", {})
    except RuntimeError as exc:
        raise ValueError(f"AnkiConnect error: {exc}") from exc

    if raw_tags is None:
        tags: List[str] = []
    else:
        if isinstance(raw_tags, (str, bytes)):
            raise ValueError("getTags response must be a sequence of strings")

        if isinstance(raw_tags, Mapping):
            raise ValueError("getTags response must be a sequence of strings")

        try:
            iterator = iter(raw_tags)
        except TypeError as exc:  # pragma: no cover - защитный хендлинг
            raise ValueError("getTags response must be a sequence of strings") from exc

        tags = []
        for index, tag in enumerate(iterator):
            if not isinstance(tag, str):
                raise ValueError(
                    f"getTags returned non-string value at index {index}: {tag!r}"
                )

            stripped = tag.strip()
            if not stripped:
                raise ValueError(f"getTags returned empty tag at index {index}")

            tags.append(stripped)

    unique: Dict[str, str] = {}
    for name in tags:
        key = name.casefold()
        unique.setdefault(key, name)

    unique_sorted = sorted(unique.values(), key=lambda name: (name.casefold(), name))

    return ListTagsResponse(tags=unique_sorted)


@app.tool(name="anki.create_deck")
async def create_deck(
    args: Union[CreateDeckArgs, Mapping[str, Any]]
) -> Any:
    if isinstance(args, CreateDeckArgs):
        normalized = args
    else:
        try:
            normalized = model_validate(CreateDeckArgs, args)
        except Exception as exc:
            raise ValueError(f"Invalid create_deck arguments: {exc}") from exc

    payload = {"deck": normalized.deck}
    return await anki_client.anki_call("createDeck", payload)


@app.tool(name="anki.get_deck_config")
async def get_deck_config(
    args: Union[GetDeckConfigArgs, Mapping[str, Any]]
) -> DeckConfig:
    if isinstance(args, GetDeckConfigArgs):
        normalized = args
    else:
        try:
            normalized = model_validate(GetDeckConfigArgs, args)
        except Exception as exc:
            raise ValueError(f"Invalid get_deck_config arguments: {exc}") from exc

    payload = {"deck": normalized.deck}
    raw_config = await anki_client.anki_call("getDeckConfig", payload)

    try:
        return model_validate(DeckConfig, raw_config)
    except Exception as exc:  # pragma: no cover - depends on validation paths
        raise ValueError(f"Invalid getDeckConfig response: {exc}") from exc


@app.tool(name="anki.save_deck_config")
async def save_deck_config(
    args: Union[SaveDeckConfigArgs, Mapping[str, Any]]
) -> Mapping[str, Any]:
    if isinstance(args, SaveDeckConfigArgs):
        normalized = args
    else:
        try:
            normalized = model_validate(SaveDeckConfigArgs, args)
        except Exception as exc:
            raise ValueError(f"Invalid save_deck_config arguments: {exc}") from exc

    config_payload = _model_dump(
        normalized.config, by_alias=True, exclude_none=True
    )
    save_result = await anki_client.anki_call(
        "saveDeckConfig", {"config": config_payload}
    )

    response: Dict[str, Any] = {
        "save_result": save_result,
    }

    config_id = normalized.config.id
    if config_id is not None:
        response["configId"] = config_id

    deck_name = normalized.deck
    if deck_name:
        if config_id is None:
            raise ValueError(
                "Deck config must include id to be assigned to a deck"
            )

        set_payload = {"deck": deck_name, "configId": config_id}
        set_result = await anki_client.anki_call("setDeckConfigId", set_payload)
        response.update({
            "deck": deck_name,
            "set_result": set_result,
        })

    return response


@app.tool(name="anki.rename_deck")
async def rename_deck(args: RenameDeckArgs):
    payload = {"oldName": args.old_name, "newName": args.new_name}
    return await anki_client.anki_call("renameDeck", payload)


@app.tool(name="anki.delete_decks")
async def delete_decks(args: DeleteDecksArgs):
    payload = {"decks": list(args.decks), "cardsToo": bool(args.cards_too)}
    return await anki_client.anki_call("deleteDecks", payload)


__all__ = [
    "list_decks",
    "list_tags",
    "create_deck",
    "get_deck_config",
    "save_deck_config",
    "rename_deck",
    "delete_decks",
]
