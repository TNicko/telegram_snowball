from __future__ import annotations

from typing import Any

from psycopg import AsyncConnection
from telethon import TelegramClient
from telethon.errors import (
    ChannelPrivateError,
    ChatAdminRequiredError,
    ChatForbiddenError,
    FloodWaitError,
)
from telethon.tl.functions.channels import GetFullChannelRequest
from telethon.tl.functions.messages import GetFullChatRequest
from telethon.tl.functions.users import GetFullUserRequest
from telethon.tl.types import Channel, Chat, User

from telegram_snowball.config import Settings
from telegram_snowball.telegram.ids import peer_type_for_entity, to_signed_peer_id
from telegram_snowball.telegram.profile_photos import harvest_profile_photo

_FULL_ERRORS = (ChannelPrivateError, ChatAdminRequiredError, ChatForbiddenError)


async def upsert_peer(conn: AsyncConnection[Any], *, entity: Any) -> int | None:
    signed = to_signed_peer_id(entity)
    if signed is None:
        return None
    peer_type = peer_type_for_entity(entity)
    title = (
        getattr(entity, "title", None)
        or " ".join(
            part
            for part in (getattr(entity, "first_name", None), getattr(entity, "last_name", None))
            if part
        )
        or None
    )
    username = getattr(entity, "username", None)
    access_hash = getattr(entity, "access_hash", None)
    await conn.execute(
        """
        INSERT INTO peers (
            external_id, peer_type, title, username, access_hash, updated_at
        )
        VALUES (%s, %s, %s, %s, %s, now())
        ON CONFLICT (external_id) DO UPDATE SET
            peer_type = EXCLUDED.peer_type,
            title = COALESCE(EXCLUDED.title, peers.title),
            username = COALESCE(EXCLUDED.username, peers.username),
            access_hash = COALESCE(EXCLUDED.access_hash, peers.access_hash),
            updated_at = now()
        """,
        (signed, peer_type, title, username, access_hash),
    )
    return signed


async def _set_full_fields(
    conn: AsyncConnection[Any],
    external_id: int,
    *,
    about: str | None,
    participants_count: int | None,
) -> None:
    await conn.execute(
        """
        UPDATE peers
        SET about = COALESCE(%s, about),
            participants_count = COALESCE(%s, participants_count),
            updated_at = now()
        WHERE external_id = %s
        """,
        (about, participants_count, external_id),
    )


def _linked_channel_from_full(full: Any, *, parent_channel_id: int) -> Channel | None:
    full_chat = getattr(full, "full_chat", None)
    linked_chat_id = getattr(full_chat, "linked_chat_id", None) if full_chat is not None else None
    if linked_chat_id is None:
        return None
    linked_id = int(linked_chat_id)
    if linked_id == int(parent_channel_id):
        return None
    for chat in getattr(full, "chats", None) or []:
        if isinstance(chat, Channel) and int(chat.id) == linked_id:
            return chat
    return None


async def materialize_peer(
    client: TelegramClient,
    conn: AsyncConnection[Any],
    *,
    settings: Settings,
    entity: Any,
    materialize_linked: bool = True,
) -> int | None:
    """Upsert peer, pull ChannelFull / ChatFull / UserFull, always try profile photo."""
    signed = await upsert_peer(conn, entity=entity)
    if signed is None:
        return None
    peer_type = peer_type_for_entity(entity)

    try:
        if isinstance(entity, Channel):
            try:
                full = await client(GetFullChannelRequest(entity))
            except _FULL_ERRORS:
                full = None
            if full is not None:
                chat_full = getattr(full, "full_chat", None)
                await _set_full_fields(
                    conn,
                    signed,
                    about=getattr(chat_full, "about", None),
                    participants_count=getattr(chat_full, "participants_count", None),
                )
                if materialize_linked:
                    linked = _linked_channel_from_full(full, parent_channel_id=int(entity.id))
                    if linked is not None:
                        await materialize_peer(
                            client,
                            conn,
                            settings=settings,
                            entity=linked,
                            materialize_linked=False,
                        )
        elif isinstance(entity, Chat):
            try:
                full = await client(GetFullChatRequest(entity.id))
            except _FULL_ERRORS:
                full = None
            if full is not None:
                chat_full = getattr(full, "full_chat", None)
                await _set_full_fields(
                    conn,
                    signed,
                    about=getattr(chat_full, "about", None),
                    participants_count=getattr(chat_full, "participants_count", None),
                )
        elif isinstance(entity, User):
            try:
                full = await client(GetFullUserRequest(entity))
            except _FULL_ERRORS:
                full = None
            if full is not None:
                user_full = getattr(full, "full_user", None)
                await _set_full_fields(
                    conn,
                    signed,
                    about=getattr(user_full, "about", None),
                    participants_count=None,
                )
    except FloodWaitError:
        raise

    photo_path = await harvest_profile_photo(
        client,
        settings=settings,
        entity=entity,
        peer_type=peer_type,
        external_id=signed,
    )
    if photo_path:
        await conn.execute(
            """
            UPDATE peers
            SET photo_path = %s,
                photo_media_kind = %s,
                updated_at = now()
            WHERE external_id = %s
            """,
            (photo_path.rel_path, photo_path.media_kind, signed),
        )
    return signed


async def refresh_connected_account(
    client: TelegramClient,
    conn: AsyncConnection[Any],
    *,
    settings: Settings,
) -> None:
    """Keep telegram_accounts in sync with get_me, including profile photo."""
    me = await client.get_me()
    if not isinstance(me, User):
        return
    await materialize_peer(
        client,
        conn,
        settings=settings,
        entity=me,
        materialize_linked=False,
    )
    signed = to_signed_peer_id(me)
    photo_row = await conn.execute(
        "SELECT photo_path, photo_media_kind FROM peers WHERE external_id = %s",
        (signed,),
    )
    photo = await photo_row.fetchone()
    photo_path = photo["photo_path"] if photo else None
    photo_media_kind = photo["photo_media_kind"] if photo else None
    await conn.execute(
        """
        UPDATE telegram_accounts
        SET phone = COALESCE(%s, phone),
            username = %s,
            first_name = %s,
            last_name = %s,
            photo_path = COALESCE(%s, photo_path),
            photo_media_kind = COALESCE(%s, photo_media_kind),
            updated_at = now()
        WHERE telegram_user_id = %s
        """,
        (
            getattr(me, "phone", None),
            getattr(me, "username", None),
            getattr(me, "first_name", None),
            getattr(me, "last_name", None),
            photo_path,
            photo_media_kind,
            int(me.id),
        ),
    )


def entity_label(entity: Any) -> str:
    if isinstance(entity, User):
        name = " ".join(
            part for part in (entity.first_name, entity.last_name) if part
        ).strip()
        if name:
            return name
        if entity.username:
            return f"@{entity.username}"
        return str(entity.id)
    if isinstance(entity, (Channel, Chat)):
        title = getattr(entity, "title", None)
        if title:
            return str(title)
        username = getattr(entity, "username", None)
        if username:
            return f"@{username}"
    signed = to_signed_peer_id(entity)
    return str(signed or "?")
