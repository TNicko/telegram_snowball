"""Local persist vs FIFO cache vs on-demand Telegram fetch for image bytes."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any
from uuid import UUID

from psycopg.types.json import Jsonb
from telethon import TelegramClient
from telethon.errors import FloodWaitError
from telethon.tl.types import Message

from telegram_snowball.config import Settings
from telegram_snowball.jobwait import JobCancelled, await_unless_cancelled, end_transaction
from telegram_snowball.phash import is_dedupable_phash, normalize_phash_hex
from telegram_snowball.telegram.profile_photos import sniff_media_bytes, sniff_profile_media, suffix_for_content_type
from telegram_snowball.telegram.resolve import entity_for_peer

lg = logging.getLogger(__name__)


async def _telegram_call(conn: Any, job_id: UUID | None, awaitable: Any) -> Any:
    if job_id is None:
        await end_transaction(conn)
        return await awaitable
    return await await_unless_cancelled(conn, job_id, awaitable)

CACHE_LIMIT = 1000
telegram_io_lock = asyncio.Lock()


def canonical_rel_path(phash: str, suffix: str) -> str:
    ext = suffix if suffix.startswith(".") else f".{suffix}" if suffix else ".jpg"
    return f"blobs/images/{phash[:2]}/{phash}{ext.lower()}"


class ImageUnavailable(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


def cache_rel_path(phash: str, suffix: str) -> str:
    ext = suffix if suffix.startswith(".") else f".{suffix}" if suffix else ".jpg"
    return f"cache/images/{phash[:2]}/{phash}{ext.lower()}"


def resolve_under_data_dir(settings: Settings, rel: str | None) -> Path | None:
    raw = str(rel or "").strip()
    if not raw or "://" in raw:
        return None
    dest = (settings.data_dir / str(rel)).resolve()
    root = settings.data_dir.resolve()
    if root not in dest.parents and dest != root:
        return None
    return dest if dest.is_file() else None


async def lookup_persisted_path(conn: Any, phash_hex: str) -> str | None:
    normalized = normalize_phash_hex(phash_hex)
    if not is_dedupable_phash(normalized):
        return None
    row = await conn.execute(
        "SELECT canonical_path FROM image_blobs WHERE phash = %s",
        (normalized,),
    )
    found = await row.fetchone()
    if found is None or not found["canonical_path"]:
        return None
    return str(found["canonical_path"])


async def persisted_file(conn: Any, settings: Settings, phash_hex: str) -> Path | None:
    rel = await lookup_persisted_path(conn, phash_hex)
    return resolve_under_data_dir(settings, rel)


async def cached_file(conn: Any, settings: Settings, phash_hex: str) -> Path | None:
    normalized = normalize_phash_hex(phash_hex)
    if not is_dedupable_phash(normalized):
        return None
    row = await conn.execute(
        "SELECT cache_path FROM image_cache WHERE phash = %s",
        (normalized,),
    )
    found = await row.fetchone()
    if found is None or not found["cache_path"]:
        return None
    dest = resolve_under_data_dir(settings, str(found["cache_path"]))
    if dest is None:
        await conn.execute("DELETE FROM image_cache WHERE phash = %s", (normalized,))
    return dest


async def image_bytes_on_disk(conn: Any, settings: Settings, phash_hex: str) -> bytes | None:
    path = await persisted_file(conn, settings, phash_hex)
    if path is None:
        path = await cached_file(conn, settings, phash_hex)
    if path is None:
        return None
    try:
        data = path.read_bytes()
    except OSError:
        return None
    return data or None


async def session_busy(conn: Any) -> bool:
    row = await conn.execute(
        "SELECT 1 FROM jobs WHERE status IN ('queued', 'running') LIMIT 1"
    )
    return await row.fetchone() is not None


def _unlink_rel(settings: Settings, rel: str | None) -> None:
    dest = resolve_under_data_dir(settings, rel)
    if dest is not None:
        dest.unlink(missing_ok=True)


async def evict_image_cache(conn: Any, settings: Settings) -> None:
    count_row = await conn.execute("SELECT COUNT(*) AS n FROM image_cache")
    total = int((await count_row.fetchone())["n"])
    extra = total - CACHE_LIMIT
    if extra <= 0:
        return
    from telegram_snowball.peer_counts import apply_phash_snapshot, phash_peer_snapshot

    doomed = await conn.execute(
        """
        SELECT phash FROM image_cache
        ORDER BY created_at ASC, phash
        LIMIT %s
        """,
        (extra,),
    )
    phashes = [str(row["phash"]) for row in await doomed.fetchall()]
    if not phashes:
        return
    before = {phash: await phash_peer_snapshot(conn, phash) for phash in phashes}
    dropped = await conn.execute(
        """
        DELETE FROM image_cache
        WHERE phash = ANY(%s)
        RETURNING phash, cache_path
        """,
        (phashes,),
    )
    for row in await dropped.fetchall():
        _unlink_rel(settings, row["cache_path"])
    for phash, snapshot in before.items():
        await apply_phash_snapshot(conn, phash, snapshot)


async def put_image_cache(
    conn: Any,
    settings: Settings,
    *,
    phash_hex: str,
    data: bytes,
    suffix: str,
) -> str:
    normalized = normalize_phash_hex(phash_hex)
    if not is_dedupable_phash(normalized):
        raise ValueError("invalid phash")
    from telegram_snowball.peer_counts import apply_phash_snapshot, phash_peer_snapshot

    before = await phash_peer_snapshot(conn, normalized)
    rel = cache_rel_path(normalized, suffix)
    dest = settings.data_dir / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    existing = await conn.execute(
        "SELECT cache_path FROM image_cache WHERE phash = %s",
        (normalized,),
    )
    prev = await existing.fetchone()
    if prev and prev["cache_path"] and str(prev["cache_path"]) != rel:
        _unlink_rel(settings, str(prev["cache_path"]))
    await conn.execute(
        """
        INSERT INTO image_cache (phash, cache_path)
        VALUES (%s, %s)
        ON CONFLICT (phash) DO UPDATE SET
            cache_path = EXCLUDED.cache_path
        """,
        (normalized, rel),
    )
    await evict_image_cache(conn, settings)
    await apply_phash_snapshot(conn, normalized, before)
    return rel


async def drop_image_cache(conn: Any, settings: Settings, phash_hex: str) -> None:
    normalized = normalize_phash_hex(phash_hex)
    if not is_dedupable_phash(normalized):
        return
    from telegram_snowball.peer_counts import apply_phash_snapshot, phash_peer_snapshot

    before = await phash_peer_snapshot(conn, normalized)
    row = await conn.execute(
        "DELETE FROM image_cache WHERE phash = %s RETURNING cache_path",
        (normalized,),
    )
    found = await row.fetchone()
    if found:
        _unlink_rel(settings, found["cache_path"])
        await apply_phash_snapshot(conn, normalized, before)


async def mark_messages_downloaded(conn: Any, phash_hex: str, *, downloaded: bool, path: str | None) -> None:
    flipped = await conn.execute(
        """
        SELECT peer_external_id, COUNT(*)::int AS n
        FROM messages
        WHERE id IN (SELECT message_id FROM image_blob_messages WHERE phash = %s)
          AND COALESCE(media->>'downloaded' IN ('true', 't', '1'), false) IS DISTINCT FROM %s
        GROUP BY peer_external_id
        """,
        (phash_hex, downloaded),
    )
    changed = await flipped.fetchall()
    await conn.execute(
        """
        UPDATE messages
        SET media = jsonb_set(
                jsonb_set(COALESCE(media, '{}'::jsonb), '{downloaded}', %s::jsonb, true),
                '{path}',
                %s::jsonb,
                true
            )
        WHERE id IN (SELECT message_id FROM image_blob_messages WHERE phash = %s)
        """,
        (Jsonb(downloaded), Jsonb(path), phash_hex),
    )
    if changed:
        from telegram_snowball.peer_counts import bump_peer_counts

        sign = 1 if downloaded else -1
        for row in changed:
            await bump_peer_counts(
                conn,
                int(row["peer_external_id"]),
                {"image_downloaded": sign * int(row["n"])},
            )


async def persist_image_bytes(
    conn: Any,
    settings: Settings,
    *,
    phash_hex: str,
    data: bytes,
    suffix: str,
) -> str:
    normalized = normalize_phash_hex(phash_hex)
    if not is_dedupable_phash(normalized):
        raise ImageUnavailable(404, "Image not found")
    from telegram_snowball.peer_counts import apply_phash_snapshot, phash_peer_snapshot

    before = await phash_peer_snapshot(conn, normalized)
    rel = canonical_rel_path(normalized, suffix)
    dest = settings.data_dir / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    await conn.execute(
        """
        UPDATE image_blobs
        SET canonical_path = %s, updated_at = now()
        WHERE phash = %s
        """,
        (rel, normalized),
    )
    await drop_image_cache(conn, settings, normalized)
    await mark_messages_downloaded(conn, normalized, downloaded=True, path=rel)
    await apply_phash_snapshot(conn, normalized, before)
    return rel


async def clear_persisted_image(conn: Any, settings: Settings, phash_hex: str) -> None:
    normalized = normalize_phash_hex(phash_hex)
    if not is_dedupable_phash(normalized):
        raise ImageUnavailable(404, "Image not found")
    row = await conn.execute(
        "SELECT canonical_path FROM image_blobs WHERE phash = %s",
        (normalized,),
    )
    found = await row.fetchone()
    if found is None:
        raise ImageUnavailable(404, "Image not found")
    from telegram_snowball.peer_counts import apply_phash_snapshot, phash_peer_snapshot

    before = await phash_peer_snapshot(conn, normalized)
    _unlink_rel(settings, found["canonical_path"])
    await conn.execute(
        """
        UPDATE image_blobs
        SET canonical_path = NULL, updated_at = now()
        WHERE phash = %s
        """,
        (normalized,),
    )
    await mark_messages_downloaded(conn, normalized, downloaded=False, path=None)
    await apply_phash_snapshot(conn, normalized, before)


async def _download_message_bytes(client: TelegramClient, message: Message) -> bytes | None:
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


async def fetch_image_from_telegram(
    client: TelegramClient,
    conn: Any,
    settings: Settings,
    phash_hex: str,
    *,
    job_id: UUID | None = None,
) -> Path:
    normalized = normalize_phash_hex(phash_hex)
    if not is_dedupable_phash(normalized):
        raise ImageUnavailable(404, "Image not found")
    sources = await conn.execute(
        """
        SELECT peer_external_id, telegram_message_id
        FROM image_blob_messages
        WHERE phash = %s AND telegram_message_id IS NOT NULL
        ORDER BY message_date DESC NULLS LAST
        LIMIT 16
        """,
        (normalized,),
    )
    rows = await sources.fetchall()
    if not rows:
        raise ImageUnavailable(404, "No Telegram source for this image")
    await end_transaction(conn)
    last_error: Exception | None = None
    for row in rows:
        peer_id = int(row["peer_external_id"])
        msg_id = int(row["telegram_message_id"])
        try:
            entity = await _telegram_call(conn, job_id, entity_for_peer(client, conn, peer_id))
            got = await _telegram_call(conn, job_id, client.get_messages(entity, ids=msg_id))
        except FloodWaitError:
            raise
        except JobCancelled:
            raise
        except Exception as exc:
            last_error = exc
            lg.info("telegram fetch skip peer %s msg %s: %s", peer_id, msg_id, exc)
            continue
        message = got[0] if isinstance(got, list) else got
        if not isinstance(message, Message):
            continue
        try:
            payload = await _telegram_call(conn, job_id, _download_message_bytes(client, message))
        except FloodWaitError:
            raise
        except JobCancelled:
            raise
        except Exception as exc:
            last_error = exc
            continue
        if not payload:
            continue
        kind, content_type = sniff_media_bytes(payload)
        if kind != "image":
            continue
        rel = await put_image_cache(
            conn,
            settings,
            phash_hex=normalized,
            data=payload,
            suffix=suffix_for_content_type(content_type),
        )
        dest = resolve_under_data_dir(settings, rel)
        if dest is None:
            continue
        return dest
    detail = "Could not reload this image from Telegram"
    if last_error is not None:
        lg.warning("telegram image reload failed for %s: %s", normalized, last_error)
    raise ImageUnavailable(404, detail)


async def ensure_local_image(
    conn: Any,
    settings: Settings,
    phash_hex: str,
    *,
    allow_telegram: bool,
    client: TelegramClient | None = None,
) -> Path:
    persisted = await persisted_file(conn, settings, phash_hex)
    if persisted is not None:
        return persisted
    cached = await cached_file(conn, settings, phash_hex)
    if cached is not None:
        return cached
    if not allow_telegram or client is None:
        raise ImageUnavailable(404, "Image is not available locally")
    return await fetch_image_from_telegram(client, conn, settings, phash_hex)


async def persist_catalog_image(
    conn: Any,
    settings: Settings,
    phash_hex: str,
    *,
    allow_telegram: bool,
    client: TelegramClient | None = None,
    job_id: UUID | None = None,
) -> str:
    existing = await persisted_file(conn, settings, phash_hex)
    if existing is not None:
        rel = await lookup_persisted_path(conn, phash_hex)
        return rel or str(existing.relative_to(settings.data_dir))
    source = await cached_file(conn, settings, phash_hex)
    if source is None:
        if not allow_telegram or client is None:
            raise ImageUnavailable(404, "Image is not available locally")
        source = await fetch_image_from_telegram(
            client, conn, settings, phash_hex, job_id=job_id
        )
    data = source.read_bytes()
    kind, content_type = sniff_profile_media(source)
    suffix = suffix_for_content_type(content_type if kind == "image" else None)
    return await persist_image_bytes(conn, settings, phash_hex=phash_hex, data=data, suffix=suffix)


def content_type_for_file(path: Path) -> str:
    kind, content_type = sniff_profile_media(path)
    if kind == "image" and content_type:
        return content_type
    return "application/octet-stream"
