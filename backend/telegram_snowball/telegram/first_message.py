from __future__ import annotations

import logging
from typing import Any

from telethon import TelegramClient
from telethon.errors import ChannelPrivateError, ChatForbiddenError, FloodWaitError, UsernameNotOccupiedError
from telethon.tl.types import Message, MessageService

from telegram_snowball.telegram.history import get_oldest_visible_page
from telegram_snowball.telegram.ids import input_peer_from_stored

lg = logging.getLogger(__name__)

_RESOLVE_ERRORS = (
    ValueError,
    UsernameNotOccupiedError,
    ChannelPrivateError,
    ChatForbiddenError,
)


async def first_message_missing(conn: Any, peer_id: int) -> bool:
    row = await conn.execute(
        "SELECT first_message_id, first_message_at FROM peers WHERE external_id = %s",
        (peer_id,),
    )
    found = await row.fetchone()
    if found is None:
        return True
    return found["first_message_at"] is None or found["first_message_id"] is None


async def record_first_visible_message(conn: Any, peer_id: int, message: Any) -> None:
    mid = getattr(message, "id", None)
    date = getattr(message, "date", None)
    if not isinstance(mid, int) or date is None:
        return
    await conn.execute(
        """
        UPDATE peers
        SET first_message_id = %s,
            first_message_at = %s,
            updated_at = now()
        WHERE external_id = %s
          AND (
            first_message_id IS NULL
            OR first_message_at IS NULL
            OR first_message_id > %s
          )
        """,
        (mid, date, peer_id, mid),
    )


async def entity_from_stored_peer(client: TelegramClient, peer: dict[str, Any]) -> Any | None:
    username = str(peer["username"]).strip() if peer.get("username") else ""
    if username:
        try:
            return await client.get_entity(username)
        except _RESOLVE_ERRORS as err:
            lg.info("username resolve failed @%s: %s", username, err)
        except FloodWaitError:
            raise
    input_peer = input_peer_from_stored(
        external_id=int(peer["external_id"]),
        peer_type=peer.get("peer_type"),
        access_hash=peer.get("access_hash"),
    )
    if input_peer is not None:
        try:
            return await client.get_entity(input_peer)
        except _RESOLVE_ERRORS as err:
            lg.info("input-peer resolve failed %s: %s", peer["external_id"], err)
        except FloodWaitError:
            raise
    return None


async def ensure_first_visible_message(
    client: TelegramClient,
    conn: Any,
    *,
    entity: Any,
    peer_id: int,
) -> bool:
    """Fetch Telegram's first visible message if we do not yet have its date."""
    if not await first_message_missing(conn, peer_id):
        return False
    try:
        page = await get_oldest_visible_page(client, entity)
    except (ChannelPrivateError, ChatForbiddenError, ValueError) as err:
        lg.info("first visible message skip peer %s: %s", peer_id, err)
        return False
    if not page.messages:
        return False
    first = page.messages[0]
    if not isinstance(first, (Message, MessageService)):
        lg.info("first visible message skip peer %s: unexpected type %s", peer_id, type(first).__name__)
        return False
    from telegram_snowball.jobs.fetch_dialogues import _persist_message
    from telegram_snowball.telegram.materialize import upsert_history_entities

    await upsert_history_entities(conn, chats=page.chats, users=page.users)
    await _persist_message(conn, peer_id=peer_id, message=first)
    await record_first_visible_message(conn, peer_id, first)
    return True


async def backfill_first_visible_message(
    conn: Any,
    settings: Any,
    peer_id: int,
) -> bool:
    """Fetch the first visible message when coverage is missing it and Telegram is idle."""
    if not await first_message_missing(conn, peer_id):
        return False
    busy = await conn.execute(
        "SELECT 1 FROM jobs WHERE status IN ('queued', 'running') LIMIT 1"
    )
    if await busy.fetchone() is not None:
        return False
    row = await conn.execute(
        """
        SELECT external_id, peer_type, username, access_hash
        FROM peers
        WHERE external_id = %s
        """,
        (peer_id,),
    )
    peer = await row.fetchone()
    if peer is None:
        return False
    from telegram_snowball.telegram.client import telegram_client

    try:
        async with telegram_client(settings) as client:
            entity = await entity_from_stored_peer(client, dict(peer))
            if entity is None:
                return False
            return await ensure_first_visible_message(
                client, conn, entity=entity, peer_id=peer_id
            )
    except FloodWaitError as err:
        lg.info("first visible message floodwait peer %s: %s", peer_id, err)
        return False
    except RuntimeError as err:
        lg.info("first visible message skip peer %s: %s", peer_id, err)
        return False
