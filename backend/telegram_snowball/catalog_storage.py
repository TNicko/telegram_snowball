"""Catalog-wide message / media counts and disk use."""

from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Any

from telegram_snowball.bytesfmt import format_bytes
from telegram_snowball.catalog import stored_kind_is
from telegram_snowball.config import Settings
from telegram_snowball.telegram.image_files import resolve_under_data_dir


def directory_bytes(root: Path) -> int:
    """Sum regular files under ``root``. Missing dirs are 0."""
    if not root.is_dir():
        return 0
    total = 0
    for dirpath, _dirnames, filenames in os.walk(root, followlinks=False):
        for name in filenames:
            path = Path(dirpath) / name
            try:
                info = path.stat()
            except OSError:
                continue
            if stat.S_ISREG(info.st_mode):
                total += int(info.st_size)
    return total


def _bucket(count: int, nbytes: int) -> dict[str, Any]:
    return {
        "count": int(count),
        "bytes": int(nbytes),
        "bytes_label": format_bytes(nbytes) or "0 B",
    }


async def catalog_storage_stats(conn: Any, settings: Settings) -> dict[str, Any]:
    messages = await (
        await conn.execute(
            """
            SELECT
              (SELECT COUNT(*) FROM messages)::bigint AS total,
              pg_total_relation_size('messages')::bigint AS bytes
            """
        )
    ).fetchone()
    images = await (
        await conn.execute(
            """
            SELECT
              COUNT(*)::bigint AS hashed,
              COUNT(*) FILTER (
                WHERE NULLIF(BTRIM(canonical_path), '') IS NOT NULL
              )::bigint AS downloaded,
              (
                pg_total_relation_size('image_blobs')
                + pg_total_relation_size('image_blob_messages')
              )::bigint AS hashed_bytes
            FROM image_blobs
            """
        )
    ).fetchone()
    videos = await (
        await conn.execute(
            f"""
            SELECT COUNT(*)::bigint AS downloaded
            FROM (
              SELECT 1
              FROM messages
              WHERE {stored_kind_is("video")}
                AND media->>'downloaded' IN ('true', 't', '1')
                AND NULLIF(BTRIM(media->>'path'), '') IS NOT NULL
              GROUP BY COALESCE(NULLIF(media->>'document_id', ''), 'msg:' || id::text)
            ) t
            """
        )
    ).fetchone()
    video_paths = await (
        await conn.execute(
            f"""
            SELECT DISTINCT media->>'path' AS path
            FROM messages
            WHERE {stored_kind_is("video")}
              AND media->>'downloaded' IN ('true', 't', '1')
              AND NULLIF(BTRIM(media->>'path'), '') IS NOT NULL
            """
        )
    ).fetchall()

    video_bytes = 0
    for row in video_paths:
        dest = resolve_under_data_dir(settings, row.get("path") if row else None)
        if dest is not None:
            try:
                video_bytes += int(dest.stat().st_size)
            except OSError:
                continue

    return {
        "messages": _bucket(int(messages["total"] or 0), int(messages["bytes"] or 0)),
        "images": _bucket(
            int(images["downloaded"] or 0),
            directory_bytes(settings.data_dir / "blobs" / "images"),
        ),
        "hashed_images": _bucket(
            int(images["hashed"] or 0),
            int(images["hashed_bytes"] or 0),
        ),
        "videos": _bucket(int(videos["downloaded"] or 0), video_bytes),
    }
