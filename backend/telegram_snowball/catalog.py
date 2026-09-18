from __future__ import annotations

from typing import Any

from telegram_snowball.telegram.media_kinds import media_kind_from_stored

_MEDIA_KINDS = ("image", "video", "audio", "gif", "document")


def attach_catalog_stats(
    peer: dict[str, Any],
    *,
    fetch_ids: set[int],
    media_cov: dict[int, dict[str, Any]],
    message_stats: dict[int, dict[str, Any]],
) -> dict[str, Any]:
    peer_id = int(peer["external_id"])
    has_fetch = peer_id in fetch_ids
    media_row = media_cov.get(peer_id)
    has_media = media_row is not None
    stats = message_stats.get(peer_id) or {}

    media: dict[str, dict[str, int] | None] = {}
    for kind in _MEDIA_KINDS:
        if has_media:
            media[kind] = {
                "total": int(stats.get(f"{kind}_total", 0) or 0),
                "downloaded": int(stats.get(f"{kind}_downloaded", 0) or 0),
            }
        else:
            media[kind] = None

    text_total = int(stats.get("text_total", 0) or 0)
    text_embedded = int(stats.get("text_embedded", 0) or 0)
    image_total = int(stats.get("image_total", 0) or 0)
    image_embedded = int(stats.get("image_embedded", 0) or 0)

    peer["has_fetch_coverage"] = has_fetch
    peer["has_media_coverage"] = has_media
    peer["posts"] = int(stats.get("posts", 0) or 0) if has_fetch else None
    peer["media"] = media
    peer["videos_excluded"] = bool(media_row["videos_excluded"]) if media_row else False
    peer["large_excluded"] = bool(media_row["large_excluded"]) if media_row else False
    peer["max_media_bytes"] = int(media_row["max_media_bytes"]) if media_row and media_row.get("max_media_bytes") else None
    peer["embed_text"] = bool(has_fetch and text_embedded >= text_total)
    peer["embed_images"] = bool(has_media and image_embedded >= image_total)
    return peer


async def load_catalog_stats(conn: Any) -> tuple[set[int], dict[int, dict[str, Any]], dict[int, dict[str, Any]]]:
    await conn.execute(
        """
        INSERT INTO peer_fetch_coverage (peer_external_id, covered_after, covered_before, updated_at)
        SELECT peer_external_id, MIN(date), MAX(date), now()
        FROM messages
        GROUP BY peer_external_id
        ON CONFLICT (peer_external_id) DO NOTHING
        """
    )
    await conn.commit()

    fetch_rows = await conn.execute("SELECT peer_external_id FROM peer_fetch_coverage")
    fetch_ids = {int(row["peer_external_id"]) for row in await fetch_rows.fetchall()}

    media_rows = await conn.execute(
        """
        SELECT peer_external_id, videos_excluded, large_excluded, max_media_bytes
        FROM peer_media_coverage
        """
    )
    media_cov = {int(row["peer_external_id"]): dict(row) for row in await media_rows.fetchall()}

    msg_rows = await conn.execute(
        """
        SELECT peer_external_id, media, content, text_embedded, image_embedded
        FROM messages
        """
    )
    items = await msg_rows.fetchall()
    message_stats: dict[int, dict[str, Any]] = {}
    for row in items:
        peer_id = int(row["peer_external_id"])
        bucket = message_stats.setdefault(
            peer_id,
            {
                "posts": 0,
                "text_total": 0,
                "text_embedded": 0,
                "image_total": 0,
                "image_embedded": 0,
                **{f"{kind}_total": 0 for kind in _MEDIA_KINDS},
                **{f"{kind}_downloaded": 0 for kind in _MEDIA_KINDS},
            },
        )
        bucket["posts"] += 1
        content = (row["content"] or "").strip()
        if content:
            bucket["text_total"] += 1
            if row["text_embedded"]:
                bucket["text_embedded"] += 1
        kind = media_kind_from_stored(row["media"])
        if kind in _MEDIA_KINDS:
            bucket[f"{kind}_total"] += 1
            downloaded = False
            media = row["media"]
            if isinstance(media, dict):
                downloaded = bool(media.get("downloaded"))
            if downloaded:
                bucket[f"{kind}_downloaded"] += 1
            if kind == "image" and row["image_embedded"]:
                bucket["image_embedded"] += 1
    return fetch_ids, media_cov, message_stats
