from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query

from telegram_snowball.api.routes.dialogues import PUBLIC_PEER_COLUMNS, public_peer
from telegram_snowball.bytesfmt import format_bytes
from telegram_snowball.config import load_settings
from telegram_snowball.db import get_conn
from telegram_snowball.telegram.forwards import origin_telegram_id_from_fwd, signed_peer_from_fwd
from telegram_snowball.telegram.media_kinds import media_kind_from_stored

router = APIRouter()

_DETAIL_SELECT = """
    id, telegram_message_id, date, content, media, fwd_from, peer_external_id
"""
_MEDIA_KINDS = frozenset({"image", "video", "audio", "gif", "document"})

_MESSAGE_PEER_COLUMNS = ", ".join(
    f"p.{col.strip()}" for col in PUBLIC_PEER_COLUMNS.strip().split(",") if col.strip()
)


def _public_message(row: dict[str, Any], *, data_dir: Any) -> dict[str, Any]:
    peer_row = {key: row[key] for key in (
        "external_id",
        "peer_type",
        "title",
        "username",
        "about",
        "participants_count",
        "photo_path",
        "photo_media_kind",
        "is_scraping",
        "scrape_detail",
        "messages_scraped",
        "last_message_id",
        "last_message_at",
        "created_at",
        "updated_at",
    )}
    content = row.get("content")
    if isinstance(content, str) and len(content) > 2000:
        content = content[:2000]
    return {
        "id": row["id"],
        "telegram_message_id": row["telegram_message_id"],
        "date": row["date"],
        "content": content,
        "from_external_id": row.get("from_external_id"),
        "forwarded": row.get("fwd_from") is not None,
        "media_kind": media_kind_from_stored(row.get("media")),
        "peer": public_peer(peer_row, data_dir=data_dir),
    }


def _as_int(value: Any) -> int | None:
    if value is None or value is False:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_float(value: Any) -> float | None:
    if value is None or value is False:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:
        return None
    return number


def _as_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _full_content(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    return value if value.strip() else None


def _iso_date(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    text = str(value).strip()
    return text or None


def media_preview(media: Any, *, kind: str | None = None, phash: str | None = None) -> dict[str, Any] | None:
    resolved = kind or media_kind_from_stored(media)
    if resolved not in _MEDIA_KINDS:
        return None
    blob = media if isinstance(media, dict) else {}
    size = _as_int(blob.get("size_bytes"))
    width = _as_int(blob.get("width"))
    height = _as_int(blob.get("height"))
    hash_hex = _as_text(phash) or _as_text(blob.get("phash"))
    file_url = f"/api/images/{hash_hex}/file" if resolved == "image" and hash_hex else None
    return {
        "kind": resolved,
        "phash": hash_hex,
        "file_url": file_url,
        "size_bytes": size,
        "size_label": format_bytes(size),
        "mime_type": _as_text(blob.get("mime_type")),
        "file_name": _as_text(blob.get("file_name")),
        "duration": _as_float(blob.get("duration")),
        "width": width,
        "height": height,
    }


def message_detail(row: dict[str, Any], *, phash: str | None = None) -> dict[str, Any]:
    kind = media_kind_from_stored(row.get("media"))
    return {
        "id": str(row["id"]),
        "telegram_message_id": row["telegram_message_id"],
        "date": _iso_date(row.get("date")),
        "content": _full_content(row.get("content")),
        "media_kind": kind,
        "media": media_preview(row.get("media"), kind=kind, phash=phash),
    }


async def _phash_for_message(conn: Any, message_id: Any, media: Any) -> str | None:
    blob = media if isinstance(media, dict) else {}
    existing = _as_text(blob.get("phash"))
    if existing:
        return existing
    found = await conn.execute(
        "SELECT phash FROM image_blob_messages WHERE message_id = %s LIMIT 1",
        (message_id,),
    )
    row = await found.fetchone()
    return _as_text(row["phash"]) if row else None


async def _load_by_id(conn: Any, message_id: UUID) -> dict[str, Any] | None:
    found = await conn.execute(
        f"SELECT {_DETAIL_SELECT} FROM messages WHERE id = %s",
        (message_id,),
    )
    row = await found.fetchone()
    return dict(row) if row else None


async def _load_by_origin(conn: Any, origin_peer_id: int, origin_telegram_id: int) -> dict[str, Any] | None:
    found = await conn.execute(
        f"""
        SELECT {_DETAIL_SELECT}
        FROM messages
        WHERE peer_external_id = %s AND telegram_message_id = %s
        LIMIT 1
        """,
        (origin_peer_id, origin_telegram_id),
    )
    row = await found.fetchone()
    if row:
        return dict(row)
    copies = await conn.execute(
        f"""
        SELECT {_DETAIL_SELECT}
        FROM messages
        WHERE fwd_from IS NOT NULL
          AND COALESCE(
                NULLIF(fwd_from->>'channel_post', ''),
                NULLIF(fwd_from->>'saved_from_msg_id', '')
              ) = %s
        ORDER BY date DESC NULLS LAST
        LIMIT 64
        """,
        (str(origin_telegram_id),),
    )
    for item in await copies.fetchall():
        data = dict(item)
        if signed_peer_from_fwd(data.get("fwd_from")) != origin_peer_id:
            continue
        if origin_telegram_id_from_fwd(data.get("fwd_from")) != origin_telegram_id:
            continue
        return data
    return None


async def _detail_payload(conn: Any, row: dict[str, Any]) -> dict[str, Any]:
    kind = media_kind_from_stored(row.get("media"))
    phash = await _phash_for_message(conn, row["id"], row.get("media")) if kind == "image" else None
    return message_detail(row, phash=phash)


@router.get("/messages")
async def list_messages(
    peer_external_id: int | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    settings = load_settings()
    async with get_conn(settings) as conn:
        if peer_external_id is not None:
            exists = await conn.execute(
                "SELECT 1 FROM peers WHERE external_id = %s",
                (peer_external_id,),
            )
            if await exists.fetchone() is None:
                raise HTTPException(status_code=404, detail="Peer not found")
            count_row = await conn.execute(
                "SELECT COUNT(*) AS n FROM messages WHERE peer_external_id = %s",
                (peer_external_id,),
            )
            rows = await conn.execute(
                f"""
                SELECT
                    m.id, m.telegram_message_id, m.date, m.content,
                    m.from_external_id, m.fwd_from, m.media,
                    {_MESSAGE_PEER_COLUMNS}
                FROM messages m
                JOIN peers p ON p.external_id = m.peer_external_id
                WHERE m.peer_external_id = %s
                ORDER BY m.date DESC, m.telegram_message_id DESC
                LIMIT %s OFFSET %s
                """,
                (peer_external_id, limit, offset),
            )
        else:
            count_row = await conn.execute("SELECT COUNT(*) AS n FROM messages")
            rows = await conn.execute(
                f"""
                SELECT
                    m.id, m.telegram_message_id, m.date, m.content,
                    m.from_external_id, m.fwd_from, m.media,
                    {_MESSAGE_PEER_COLUMNS}
                FROM messages m
                JOIN peers p ON p.external_id = m.peer_external_id
                ORDER BY m.date DESC, m.telegram_message_id DESC
                LIMIT %s OFFSET %s
                """,
                (limit, offset),
            )
        total = int((await count_row.fetchone())["n"])
        items = await rows.fetchall()
    return {
        "messages": [_public_message(dict(row), data_dir=settings.data_dir) for row in items],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/messages/lookup")
async def lookup_message(
    origin_peer_id: int = Query(...),
    origin_telegram_id: int = Query(..., ge=1),
) -> dict[str, Any]:
    settings = load_settings()
    async with get_conn(settings) as conn:
        row = await _load_by_origin(conn, origin_peer_id, origin_telegram_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Message not found")
        return await _detail_payload(conn, row)


@router.get("/messages/{message_id}")
async def get_message(message_id: UUID) -> dict[str, Any]:
    settings = load_settings()
    async with get_conn(settings) as conn:
        row = await _load_by_id(conn, message_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Message not found")
        return await _detail_payload(conn, row)
