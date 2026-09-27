"""Resolve a stored peer to a Telethon entity for on-demand media fetches."""

from __future__ import annotations

import logging
from typing import Any

from telethon import TelegramClient
from telethon.errors import ChannelPrivateError, ChatForbiddenError, UsernameNotOccupiedError

from telegram_snowball.telegram.ids import input_peer_from_stored

lg = logging.getLogger(__name__)

_RESOLVE_ERRORS = (ValueError, UsernameNotOccupiedError, ChannelPrivateError, ChatForbiddenError)


async def entity_for_peer(client: TelegramClient, conn: Any, peer_id: int) -> Any:
    row = await conn.execute(
        "SELECT username, access_hash, peer_type FROM peers WHERE external_id = %s",
        (peer_id,),
    )
    found = await row.fetchone()
    if found is not None:
        username = str(found["username"]).strip() if found.get("username") else ""
        if username:
            try:
                return await client.get_entity(username)
            except _RESOLVE_ERRORS as err:
                lg.info("username resolve failed @%s: %s", username, err)
        input_peer = input_peer_from_stored(
            external_id=int(peer_id),
            peer_type=found.get("peer_type"),
            access_hash=found.get("access_hash"),
        )
        if input_peer is not None:
            try:
                return await client.get_entity(input_peer)
            except _RESOLVE_ERRORS as err:
                lg.info("input-peer resolve failed %s: %s", peer_id, err)
    return await client.get_entity(peer_id)
