"""Canonical image blobs keyed by exact pHash, plus message fan-out."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from psycopg.types.json import Jsonb
from telethon import TelegramClient
from telethon.errors import FloodWaitError
from telethon.tl.types import Message

from telegram_snowball.config import Settings
from telegram_snowball.jsonutil import json_safe
from telegram_snowball.phash import is_dedupable_phash, normalize_phash_hex, phash_hex_from_bytes
from telegram_snowball.telegram.image_files import persist_image_bytes, persisted_file, put_image_cache
from telegram_snowball.telegram.profile_photos import sniff_media_bytes, suffix_for_content_type

lg = logging.getLogger(__name__)


def _as_uuid(value: UUID | str | None) -> UUID | None:
    if isinstance(value, UUID):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return UUID(value.strip())
        except ValueError:
            return None
    return None


async def lookup_canonical_path(conn: Any, phash_hex: str) -> str | None:
    normalized = normalize_phash_hex(phash_hex)
    if normalized is None or not is_dedupable_phash(normalized):
        return None
    row = await conn.execute(
        "SELECT canonical_path FROM image_blobs WHERE phash = %s",
        (normalized,),
    )
    found = await row.fetchone()
    if found is None or not found["canonical_path"]:
        return None
    return str(found["canonical_path"])


async def link_blob_message(
    conn: Any,
    *,
    phash_hex: str | None,
    message_id: UUID | str | None,
    message_date: datetime | None,
    peer_external_id: int | None,
    telegram_message_id: int | None = None,
) -> None:
    normalized = normalize_phash_hex(phash_hex)
    message_uuid = _as_uuid(message_id)
    if (
        not is_dedupable_phash(normalized)
        or message_uuid is None
        or message_date is None
        or peer_external_id is None
    ):
        return
    await conn.execute(
        """
        INSERT INTO image_blob_messages (
            phash, message_id, message_date, peer_external_id, telegram_message_id
        )
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (phash, message_id) DO UPDATE SET
            message_date = EXCLUDED.message_date,
            peer_external_id = EXCLUDED.peer_external_id,
            telegram_message_id = COALESCE(
                EXCLUDED.telegram_message_id, image_blob_messages.telegram_message_id
            )
        """,
        (normalized, message_uuid, message_date, int(peer_external_id), telegram_message_id),
    )
    await conn.execute(
        """
        UPDATE image_blobs
        SET refcount = (
                SELECT COUNT(*) FROM image_blob_messages WHERE phash = %s
            ),
            updated_at = now()
        WHERE phash = %s
        """,
        (normalized, normalized),
    )


async def record_harvested_image_blob(
    conn: Any,
    *,
    phash_hex: str | None,
    canonical_path: str | None,
    message_id: UUID | str | None,
    message_date: datetime | None,
    peer_external_id: int | None,
    telegram_message_id: int | None = None,
) -> str | None:
    normalized = normalize_phash_hex(phash_hex)
    if not is_dedupable_phash(normalized):
        return canonical_path
    row = await conn.execute(
        """
        INSERT INTO image_blobs (phash, canonical_path, refcount)
        VALUES (%s, %s, 1)
        ON CONFLICT (phash) DO UPDATE SET
            canonical_path = COALESCE(image_blobs.canonical_path, EXCLUDED.canonical_path),
            updated_at = now()
        RETURNING canonical_path
        """,
        (normalized, canonical_path),
    )
    stored = await row.fetchone()
    keeper = None
    if stored and stored["canonical_path"]:
        keeper = str(stored["canonical_path"])
    elif canonical_path:
        keeper = canonical_path
    await link_blob_message(
        conn,
        phash_hex=normalized,
        message_id=message_id,
        message_date=message_date,
        peer_external_id=peer_external_id,
        telegram_message_id=telegram_message_id,
    )
    return keeper


async def _download_image_bytes(client: TelegramClient, message: Message) -> bytes | None:
    saved = await client.download_media(message, file=bytes)
    if isinstance(saved, (bytes, bytearray)) and saved:
        return bytes(saved)
    if isinstance(saved, str) and saved:
        path = Path(saved)
        try:
            return path.read_bytes()
        finally:
            path.unlink(missing_ok=True)
    return None


async def harvest_message_image(
    client: TelegramClient,
    conn: Any,
    *,
    settings: Settings,
    message: Message,
    message_uuid: UUID,
    peer_id: int,
    media: dict[str, Any] | None,
    persist: bool = False,
) -> bool:
    """Temporarily download an image, pHash it, fan out, optionally persist the file."""
    existing = dict(media) if isinstance(media, dict) else {}
    already = existing.get("phash")
    if not is_dedupable_phash(already if isinstance(already, str) else None):
        linked = await conn.execute(
            """
            SELECT ibm.phash, b.canonical_path
            FROM image_blob_messages ibm
            JOIN image_blobs b ON b.phash = ibm.phash
            WHERE ibm.message_id = %s
            LIMIT 1
            """,
            (message_uuid,),
        )
        row = await linked.fetchone()
        if row and is_dedupable_phash(str(row["phash"]) if row["phash"] else None):
            already = str(row["phash"])
            existing["phash"] = already
            if row["canonical_path"]:
                existing["path"] = str(row["canonical_path"])
    if is_dedupable_phash(already if isinstance(already, str) else None):
        phash = str(already)
        keeper = await lookup_canonical_path(conn, phash)
        have_file = await persisted_file(conn, settings, phash)
        if persist and have_file is None:
            pass
        else:
            await record_harvested_image_blob(
                conn,
                phash_hex=phash,
                canonical_path=keeper,
                message_id=message_uuid,
                message_date=message.date,
                peer_external_id=peer_id,
                telegram_message_id=int(message.id),
            )
            next_media = dict(existing)
            next_media["kind"] = next_media.get("kind") or "image"
            next_media["phash"] = phash
            next_media["downloaded"] = have_file is not None
            if keeper:
                next_media["path"] = keeper
            await conn.execute(
                "UPDATE messages SET media = %s WHERE id = %s",
                (Jsonb(json_safe(next_media)), message_uuid),
            )
            return True

    try:
        payload = await _download_image_bytes(client, message)
    except FloodWaitError:
        raise
    except Exception as exc:
        lg.warning("image download failed for peer %s msg %s: %s", peer_id, message.id, exc)
        return False
    if not payload:
        return False

    kind, content_type = sniff_media_bytes(payload)
    if kind != "image":
        return False
    suffix = suffix_for_content_type(content_type)

    try:
        phash = phash_hex_from_bytes(payload)
    except Exception as exc:
        lg.warning("pHash failed for peer %s msg %s: %s", peer_id, message.id, exc)
        return False
    if not is_dedupable_phash(phash):
        return False

    keeper: str | None = None
    if persist:
        await record_harvested_image_blob(
            conn,
            phash_hex=phash,
            canonical_path=None,
            message_id=message_uuid,
            message_date=message.date,
            peer_external_id=peer_id,
            telegram_message_id=int(message.id),
        )
        keeper = await persist_image_bytes(
            conn, settings, phash_hex=phash, data=payload, suffix=suffix
        )
    else:
        keeper = await record_harvested_image_blob(
            conn,
            phash_hex=phash,
            canonical_path=None,
            message_id=message_uuid,
            message_date=message.date,
            peer_external_id=peer_id,
            telegram_message_id=int(message.id),
        )
        already_file = await persisted_file(conn, settings, phash)
        if already_file is None:
            await put_image_cache(conn, settings, phash_hex=phash, data=payload, suffix=suffix)
            keeper = None
        else:
            keeper = str(already_file.relative_to(settings.data_dir))

    next_media = dict(existing)
    next_media["kind"] = next_media.get("kind") or "image"
    next_media["phash"] = phash
    next_media["downloaded"] = bool(keeper)
    if keeper:
        next_media["path"] = keeper
    else:
        next_media.pop("path", None)
    await conn.execute(
        "UPDATE messages SET media = %s WHERE id = %s",
        (Jsonb(json_safe(next_media)), message_uuid),
    )
    return True
