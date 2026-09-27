from __future__ import annotations

from typing import Any

from psycopg import AsyncConnection
from psycopg.types.json import Jsonb
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
from telethon.tl.types import Channel, ChannelForbidden, Chat, ChatForbidden, User

from telegram_snowball.config import Settings
from telegram_snowball.jsonutil import json_safe
from telegram_snowball.telegram.ids import infer_peer_type_from_signed, peer_type_for_entity, to_signed_peer_id
from telegram_snowball.telegram.profile import full_profile_from_full, min_profile_from_entity
from telegram_snowball.telegram.profile_photos import harvest_profile_photo

_FULL_ERRORS = (ChannelPrivateError, ChatAdminRequiredError, ChatForbiddenError)
_JSON_KEYS = frozenset({"usernames", "restriction_reason"})
_PROFILE_COLUMNS = (
    "title",
    "first_name",
    "last_name",
    "username",
    "usernames",
    "telegram_date",
    "verified",
    "scam",
    "fake",
    "restricted",
    "restriction_reason",
    "noforwards",
    "forum",
    "gigagroup",
    "join_to_send",
    "join_request",
    "has_link",
    "has_geo",
    "deleted",
    "premium",
    "deactivated",
    "slowmode_enabled",
    "linked_monoforum_id",
    "migrated_to_channel_id",
    "participants_count",
    "about",
    "linked_chat_id",
    "migrated_from_chat_id",
    "slowmode_seconds",
    "hidden_prehistory",
    "available_min_id",
    "participants_hidden",
    "admins_count",
    "kicked_count",
    "banned_count",
    "online_count",
    "ttl_period",
    "pinned_msg_id",
    "location_address",
    "location_lat",
    "location_lng",
    "common_chats_count",
)


def _sql_value(key: str, value: Any) -> Any:
    if value is None:
        return None
    if key in _JSON_KEYS:
        return Jsonb(json_safe(value))
    return value


async def _apply_peer_fields(
    conn: AsyncConnection[Any],
    external_id: int,
    fields: dict[str, Any],
) -> None:
    assignments: list[str] = []
    values: list[Any] = []
    for key in _PROFILE_COLUMNS:
        if key not in fields:
            continue
        value = fields[key]
        if value is None:
            continue
        assignments.append(f"{key} = COALESCE(%s, {key})")
        values.append(_sql_value(key, value))
    if not assignments:
        return
    assignments.append("updated_at = now()")
    values.append(external_id)
    await conn.execute(
        f"UPDATE peers SET {', '.join(assignments)} WHERE external_id = %s",
        tuple(values),
    )


async def upsert_peer(conn: AsyncConnection[Any], *, entity: Any) -> int | None:
    signed = to_signed_peer_id(entity)
    if signed is None:
        return None
    peer_type = peer_type_for_entity(entity)
    profile = min_profile_from_entity(entity)
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
        (signed, peer_type, profile.get("title"), profile.get("username"), access_hash),
    )
    await _apply_peer_fields(conn, signed, profile)
    return signed


async def upsert_peer_stub(
    conn: AsyncConnection[Any],
    *,
    external_id: int,
    peer_type: str | None = None,
    title: str | None = None,
) -> int:
    """Insert a catalog row for a discovered peer without a Telethon entity yet."""
    kind = peer_type or infer_peer_type_from_signed(external_id)
    await conn.execute(
        """
        INSERT INTO peers (external_id, peer_type, title, updated_at)
        VALUES (%s, %s, %s, now())
        ON CONFLICT (external_id) DO UPDATE SET
            title = COALESCE(peers.title, EXCLUDED.title),
            updated_at = now()
        """,
        (external_id, kind, title),
    )
    return external_id


async def upsert_history_entities(
    conn: AsyncConnection[Any],
    *,
    chats: list[Any],
    users: list[Any],
) -> int:
    """Light-upsert community stubs from a GetHistory ``chats[]`` into Catalog."""
    seen: set[int] = set()
    count = 0
    for entity in (*(chats or []), *(users or [])):
        if not isinstance(entity, (Channel, ChannelForbidden, Chat, ChatForbidden)):
            continue
        signed = to_signed_peer_id(entity)
        if signed is None or signed in seen:
            continue
        seen.add(signed)
        if await upsert_peer(conn, entity=entity) is not None:
            count += 1
    return count


async def _set_full_fields(
    conn: AsyncConnection[Any],
    external_id: int,
    *,
    full: Any,
    entity: Any | None = None,
) -> None:
    await _apply_peer_fields(conn, external_id, full_profile_from_full(full, entity=entity))


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
    fetch_first_message: bool = True,
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
                await _set_full_fields(conn, signed, full=full, entity=entity)
                if materialize_linked:
                    linked = _linked_channel_from_full(full, parent_channel_id=int(entity.id))
                    if linked is not None:
                        await materialize_peer(
                            client,
                            conn,
                            settings=settings,
                            entity=linked,
                            materialize_linked=False,
                            fetch_first_message=False,
                        )
        elif isinstance(entity, Chat):
            try:
                full = await client(GetFullChatRequest(entity.id))
            except _FULL_ERRORS:
                full = None
            if full is not None:
                await _set_full_fields(conn, signed, full=full, entity=entity)
        elif isinstance(entity, User):
            try:
                full = await client(GetFullUserRequest(entity))
            except _FULL_ERRORS:
                full = None
            if full is not None:
                await _set_full_fields(conn, signed, full=full, entity=entity)
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
    if fetch_first_message:
        from telegram_snowball.telegram.first_message import ensure_first_visible_message

        try:
            await ensure_first_visible_message(client, conn, entity=entity, peer_id=signed)
        except FloodWaitError:
            raise
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
        fetch_first_message=False,
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
