"""Raw ``messages.GetHistory`` pages, including sibling ``chats[]`` / ``users[]``."""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import Any

from telethon import TelegramClient, utils as tg_utils
from telethon.tl.functions.messages import GetHistoryRequest
from telethon.tl.types import MessageEmpty

from telegram_snowball.telegram.ids import to_signed_peer_id

HISTORY_LIMIT = 100


@dataclass(frozen=True, slots=True)
class HistoryPage:
    messages: list[Any]
    chats: list[Any] = field(default_factory=list)
    users: list[Any] = field(default_factory=list)


def messages_from_history_result(client: TelegramClient, result: Any, entity: Any) -> list[Any]:
    if result is None or not hasattr(result, "messages"):
        return []
    chats = getattr(result, "chats", None) or []
    users = getattr(result, "users", None) or []
    entities: dict[int, Any] = {}
    for item in itertools.chain(users, chats):
        try:
            entities[tg_utils.get_peer_id(item)] = item
        except Exception:
            continue
    out: list[Any] = []
    for message in result.messages:
        if message is None or isinstance(message, MessageEmpty):
            continue
        if getattr(message, "id", None) is None:
            continue
        message._finish_init(client, entities, entity)
        out.append(message)
    return out


def chats_by_signed_id(chats: list[Any]) -> dict[int, Any]:
    out: dict[int, Any] = {}
    for chat in chats:
        signed = to_signed_peer_id(chat)
        if signed is not None:
            out[signed] = chat
    return out


async def get_oldest_visible_page(client: TelegramClient, entity: Any) -> HistoryPage:
    """First visible message in the peer (offset 1 / add_offset -1)."""
    result = await client(
        GetHistoryRequest(
            peer=entity,
            offset_id=1,
            offset_date=None,
            add_offset=-1,
            limit=1,
            max_id=0,
            min_id=0,
            hash=0,
        )
    )
    chats = list(getattr(result, "chats", None) or [])
    users = list(getattr(result, "users", None) or [])
    return HistoryPage(
        messages=messages_from_history_result(client, result, entity),
        chats=chats,
        users=users,
    )


async def get_history_page(
    client: TelegramClient,
    entity: Any,
    *,
    offset_id: int = 0,
    min_id: int = 0,
    limit: int = HISTORY_LIMIT,
) -> HistoryPage:
    result = await client(
        GetHistoryRequest(
            peer=entity,
            offset_id=offset_id,
            offset_date=None,
            add_offset=0,
            limit=limit,
            max_id=0,
            min_id=min_id,
            hash=0,
        )
    )
    chats = list(getattr(result, "chats", None) or [])
    users = list(getattr(result, "users", None) or [])
    return HistoryPage(
        messages=messages_from_history_result(client, result, entity),
        chats=chats,
        users=users,
    )
