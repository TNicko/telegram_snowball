from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

_MEDIA_KINDS = ("image", "video", "audio", "gif", "document")

# Matches telegram.media_kinds.media_kind_from_stored in SQL.
# Reclassifies stored "document" rows from mime_type / file_name when Telegram
# sent an image or video as a file.
_STORED_MEDIA_KIND_SQL = """
COALESCE(
  CASE WHEN media->>'kind' IN ('image', 'gif', 'video', 'audio')
       THEN media->>'kind' END,
  CASE
    WHEN lower(COALESCE(media->>'mime_type', '')) = 'image/gif' THEN 'gif'
    WHEN lower(COALESCE(media->>'mime_type', '')) ~ '^image/'
         AND position('svg' in lower(COALESCE(media->>'mime_type', ''))) = 0
         AND position('dwg' in lower(COALESCE(media->>'mime_type', ''))) = 0
      THEN 'image'
    WHEN lower(COALESCE(media->>'mime_type', '')) ~ '^video/' THEN 'video'
    WHEN lower(COALESCE(media->>'mime_type', '')) ~ '^audio/' THEN 'audio'
  END,
  CASE
    WHEN lower(COALESCE(media->>'file_name', '')) ~* '\\.gif$' THEN 'gif'
    WHEN lower(COALESCE(media->>'file_name', ''))
         ~* '\\.(jpe?g|png|webp|bmp|tiff?|heic|heif|avif|jfif)$' THEN 'image'
    WHEN lower(COALESCE(media->>'file_name', ''))
         ~* '\\.(mp4|m4v|mov|mkv|webm|avi|3gp|mpeg|mpg)$' THEN 'video'
    WHEN lower(COALESCE(media->>'file_name', ''))
         ~* '\\.(mp3|m4a|ogg|oga|flac|wav|opus|aac)$' THEN 'audio'
  END,
  CASE WHEN media->>'kind' = 'document' THEN 'document' END,
  CASE media->>'tl'
    WHEN 'MessageMediaPhoto' THEN 'image'
    WHEN 'MessageMediaDocument' THEN 'document'
  END
)
"""


def stored_kind_is(kind: str) -> str:
    if kind not in _MEDIA_KINDS:
        raise ValueError(f"unknown media kind {kind}")
    return f"({_STORED_MEDIA_KIND_SQL.strip()}) = '{kind}'"

_IMAGE_HAS_PHASH_SQL = "COALESCE(NULLIF(BTRIM(media->>'phash'), ''), '') <> ''"


def _as_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def time_coverage_ratio(
    origin: Any,
    now: Any,
    covered_after: Any,
) -> float:
    """Newest-first scrape: share of [origin, now] already walked back from now."""
    start = _as_datetime(origin)
    end = _as_datetime(now)
    after = _as_datetime(covered_after)
    if start is None or end is None or after is None:
        return 0.0
    total = (end - start).total_seconds()
    if total <= 0:
        return 1.0
    walked = (end - after).total_seconds()
    return max(0.0, min(1.0, walked / total))


def _iso(value: Any) -> str | None:
    parsed = _as_datetime(value)
    return parsed.isoformat() if parsed is not None else None


def _empty_message_stats() -> dict[str, Any]:
    return {
        "posts": 0,
        "text_total": 0,
        "text_embedded": 0,
        "image_total": 0,
        "image_hashed": 0,
        "image_embedded": 0,
        "image_unique": 0,
        "image_persisted": 0,
        "image_embeddable": 0,
        "image_embedded_unique": 0,
        "unique_forwards": 0,
        "total_forwards": 0,
        **{f"{kind}_total": 0 for kind in _MEDIA_KINDS},
        **{f"{kind}_downloaded": 0 for kind in _MEDIA_KINDS},
        **{f"{kind}_after": None for kind in _MEDIA_KINDS},
        **{f"{kind}_before": None for kind in _MEDIA_KINDS},
        "text_embed_after": None,
        "text_embed_before": None,
        "image_embed_after": None,
        "image_embed_before": None,
    }


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
    image_unique = int(stats.get("image_unique", 0) or 0)
    image_persisted = int(stats.get("image_persisted", 0) or 0)
    image_hashed = int(stats.get("image_hashed", 0) or 0)
    for kind in _MEDIA_KINDS:
        total = int(stats.get(f"{kind}_total", 0) or 0)
        downloaded = int(stats.get(f"{kind}_downloaded", 0) or 0)
        if kind == "image":
            downloaded = image_persisted if image_persisted > 0 else downloaded
            if has_media or total > 0 or downloaded > 0 or image_hashed > 0 or image_unique > 0:
                media[kind] = {
                    "total": total,
                    "hashed": image_hashed,
                    "downloaded": downloaded,
                    "unique": image_unique,
                }
            else:
                media[kind] = None
            continue
        if has_media or total > 0 or downloaded > 0:
            media[kind] = {"total": total, "downloaded": downloaded}
        else:
            media[kind] = None

    text_total = int(stats.get("text_total", 0) or 0)
    text_embedded = int(stats.get("text_embedded", 0) or 0)
    if "image_embeddable" in stats:
        image_total = int(stats.get("image_embeddable", 0) or 0)
        image_embedded = int(stats.get("image_embedded_unique", stats.get("image_embedded", 0)) or 0)
    else:
        image_total = image_unique or int(stats.get("image_total", 0) or 0)
        image_embedded = int(stats.get("image_embedded", 0) or 0)

    posts = int(stats.get("posts", 0) or 0)
    scraped = int(peer.get("messages_scraped") or 0)
    shown_posts = posts if posts > 0 else scraped

    peer["has_fetch_coverage"] = has_fetch
    peer["has_media_coverage"] = has_media or image_unique > 0
    peer["posts"] = shown_posts if (has_fetch or shown_posts > 0) else None
    unique_forwards = int(stats.get("unique_forwards", 0) or 0)
    total_forwards = int(stats.get("total_forwards", 0) or 0)
    if has_fetch or unique_forwards > 0 or total_forwards > 0:
        peer["forwards_unique"] = unique_forwards
        peer["forwards_total"] = total_forwards
    else:
        peer["forwards_unique"] = None
        peer["forwards_total"] = None
    peer["media"] = media
    peer["videos_excluded"] = bool(media_row["videos_excluded"]) if media_row else False
    peer["large_excluded"] = bool(media_row["large_excluded"]) if media_row else False
    peer["max_media_bytes"] = int(media_row["max_media_bytes"]) if media_row and media_row.get("max_media_bytes") else None
    scraped = bool(has_fetch or shown_posts > 0)
    peer["embed_text"] = {"done": text_embedded, "total": text_total} if scraped and text_total > 0 else None
    peer["embed_images"] = (
        {"done": image_embedded, "total": image_total} if scraped and image_total > 0 else None
    )
    return peer


async def load_catalog_stats(conn: Any) -> tuple[set[int], dict[int, dict[str, Any]], dict[int, dict[str, Any]]]:
    fetch_rows = await conn.execute("SELECT peer_external_id FROM peer_fetch_coverage")
    fetch_ids = {int(row["peer_external_id"]) for row in await fetch_rows.fetchall()}

    media_rows = await conn.execute(
        """
        SELECT peer_external_id, videos_excluded, large_excluded, max_media_bytes
        FROM peer_media_coverage
        """
    )
    media_cov = {int(row["peer_external_id"]): dict(row) for row in await media_rows.fetchall()}

    from telegram_snowball.peer_counts import load_peer_count_map

    stored = await load_peer_count_map(conn)
    message_stats: dict[int, dict[str, Any]] = {}
    for peer_id, counts in stored.items():
        bucket = _empty_message_stats()
        bucket.update(counts)
        message_stats[peer_id] = bucket
    return fetch_ids, media_cov, message_stats


def _window(row: dict[str, Any] | None, *extra: str) -> dict[str, Any] | None:
    if not row:
        return None
    out: dict[str, Any] = {
        "covered_after": row.get("covered_after"),
        "covered_before": row.get("covered_before"),
        "updated_at": row.get("updated_at"),
    }
    for key in extra:
        out[key] = row.get(key)
    return out


def _layer_fill(origin: Any, now: Any, covered_after: Any) -> float:
    return round(time_coverage_ratio(origin, now, covered_after), 4)


def build_peer_coverage(
    peer: dict[str, Any],
    *,
    fetch: dict[str, Any] | None,
    media: dict[str, Any] | None,
    stats: dict[str, Any] | None,
    now: datetime | None = None,
) -> dict[str, Any]:
    peer_id = int(peer["external_id"])
    stats = stats or _empty_message_stats()
    fetch_ids = {peer_id} if fetch else set()
    media_cov = {peer_id: media} if media else {}
    attach_catalog_stats(
        peer,
        fetch_ids=fetch_ids,
        media_cov=media_cov,
        message_stats={peer_id: stats},
    )
    moment = now or datetime.now(timezone.utc)
    origin = peer.get("first_message_at")
    text_total = int(stats.get("text_total", 0) or 0)
    text_embedded = int(stats.get("text_embedded", 0) or 0)
    if "image_embeddable" in stats:
        image_total = int(stats.get("image_embeddable", 0) or 0)
        image_embedded = int(stats.get("image_embedded_unique", stats.get("image_embedded", 0)) or 0)
    else:
        image_total = int(stats.get("image_unique", 0) or stats.get("image_total", 0) or 0)
        image_embedded = int(stats.get("image_embedded", 0) or 0)
    posts_after = (fetch or {}).get("covered_after")
    posts_fill = _layer_fill(origin, moment, posts_after)
    media_layers: dict[str, dict[str, Any]] = {}
    for kind in _MEDIA_KINDS:
        after = stats.get(f"{kind}_after")
        before = stats.get(f"{kind}_before")
        media_layers[kind] = {
            "covered_after": _iso(after),
            "covered_before": _iso(before),
            "fill": _layer_fill(origin, moment, after),
        }
    return {
        "peer": peer,
        "timeline": {
            "start": _iso(origin),
            "end": _iso(moment),
            "first_message_id": peer.get("first_message_id") or (fetch or {}).get("first_message_id"),
        },
        "posts": {
            **(_window(fetch) or {"covered_after": None, "covered_before": None, "updated_at": None}),
            "count": peer.get("posts"),
            "fill": posts_fill,
        },
        "media_pass": _window(
            media,
            "videos_excluded",
            "large_excluded",
            "max_media_bytes",
        ),
        "media_layers": media_layers,
        "forwards": {"fill": posts_fill if int(peer.get("forwards_total") or 0) else 0.0},
        "embeds": {
            "text": {
                "total": text_total,
                "done": text_embedded,
                "covered_after": _iso(stats.get("text_embed_after")),
                "covered_before": _iso(stats.get("text_embed_before")),
                "fill": _layer_fill(origin, moment, stats.get("text_embed_after")),
            },
            "images": {
                "total": image_total,
                "done": image_embedded,
                "covered_after": _iso(stats.get("image_embed_after")),
                "covered_before": _iso(stats.get("image_embed_before")),
                "fill": _layer_fill(origin, moment, stats.get("image_embed_after")),
            },
        },
    }


async def load_peer_message_stats(conn: Any, peer_id: int) -> dict[str, Any]:
    from telegram_snowball.peer_counts import load_peer_count

    kind = _STORED_MEDIA_KIND_SQL.strip()
    stats = _empty_message_stats()
    stats.update(await load_peer_count(conn, peer_id))
    row = await conn.execute(
        f"""
        SELECT
            MIN(date) FILTER (
                WHERE ({kind}) = 'image' AND {_IMAGE_HAS_PHASH_SQL}
            ) AS image_after,
            MAX(date) FILTER (
                WHERE ({kind}) = 'image' AND {_IMAGE_HAS_PHASH_SQL}
            ) AS image_before,
            MIN(date) FILTER (
                WHERE ({kind}) = 'video' AND media->>'downloaded' IN ('true', 't', '1')
            ) AS video_after,
            MAX(date) FILTER (
                WHERE ({kind}) = 'video' AND media->>'downloaded' IN ('true', 't', '1')
            ) AS video_before,
            MIN(date) FILTER (
                WHERE ({kind}) = 'audio' AND media->>'downloaded' IN ('true', 't', '1')
            ) AS audio_after,
            MAX(date) FILTER (
                WHERE ({kind}) = 'audio' AND media->>'downloaded' IN ('true', 't', '1')
            ) AS audio_before,
            MIN(date) FILTER (
                WHERE ({kind}) = 'gif' AND media->>'downloaded' IN ('true', 't', '1')
            ) AS gif_after,
            MAX(date) FILTER (
                WHERE ({kind}) = 'gif' AND media->>'downloaded' IN ('true', 't', '1')
            ) AS gif_before,
            MIN(date) FILTER (
                WHERE ({kind}) = 'document' AND media->>'downloaded' IN ('true', 't', '1')
            ) AS document_after,
            MAX(date) FILTER (
                WHERE ({kind}) = 'document' AND media->>'downloaded' IN ('true', 't', '1')
            ) AS document_before,
            MIN(date) FILTER (
                WHERE NULLIF(BTRIM(content), '') IS NOT NULL AND text_embedded
            ) AS text_embed_after,
            MAX(date) FILTER (
                WHERE NULLIF(BTRIM(content), '') IS NOT NULL AND text_embedded
            ) AS text_embed_before,
            MIN(date) FILTER (WHERE ({kind}) = 'image' AND image_embedded) AS image_embed_after,
            MAX(date) FILTER (WHERE ({kind}) = 'image' AND image_embedded) AS image_embed_before
        FROM messages
        WHERE peer_external_id = %s
        """,
        (peer_id,),
    )
    data = await row.fetchone()
    if data is not None:
        for media_kind in _MEDIA_KINDS:
            stats[f"{media_kind}_after"] = data.get(f"{media_kind}_after")
            stats[f"{media_kind}_before"] = data.get(f"{media_kind}_before")
        stats["text_embed_after"] = data.get("text_embed_after")
        stats["text_embed_before"] = data.get("text_embed_before")
        stats["image_embed_after"] = data.get("image_embed_after")
        stats["image_embed_before"] = data.get("image_embed_before")
    if stats.get("image_after") is None and int(stats.get("image_unique") or 0) > 0:
        hashed_span = await conn.execute(
            """
            SELECT MIN(message_date) AS image_after, MAX(message_date) AS image_before
            FROM image_blob_messages
            WHERE peer_external_id = %s
            """,
            (peer_id,),
        )
        span = await hashed_span.fetchone()
        if span is not None:
            stats["image_after"] = span["image_after"]
            stats["image_before"] = span["image_before"]
    return stats


async def load_peer_coverage(conn: Any, peer: dict[str, Any]) -> dict[str, Any]:
    peer_id = int(peer["external_id"])
    fetch_row = await conn.execute(
        """
        SELECT covered_after, covered_before, updated_at
        FROM peer_fetch_coverage
        WHERE peer_external_id = %s
        """,
        (peer_id,),
    )
    fetch = await fetch_row.fetchone()
    media_row = await conn.execute(
        """
        SELECT covered_after, covered_before, videos_excluded, large_excluded,
               max_media_bytes, updated_at
        FROM peer_media_coverage
        WHERE peer_external_id = %s
        """,
        (peer_id,),
    )
    media = await media_row.fetchone()
    stats = await load_peer_message_stats(conn, peer_id)
    first = await conn.execute(
        """
        SELECT first_message_id, first_message_at
        FROM peers
        WHERE external_id = %s
        """,
        (peer_id,),
    )
    first_row = await first.fetchone()
    if first_row is not None:
        peer["first_message_id"] = first_row["first_message_id"]
        peer["first_message_at"] = first_row["first_message_at"]
        if peer["first_message_at"] is None and first_row["first_message_id"] is not None:
            stored = await conn.execute(
                """
                SELECT date
                FROM messages
                WHERE peer_external_id = %s AND telegram_message_id = %s
                """,
                (peer_id, int(first_row["first_message_id"])),
            )
            stored_row = await stored.fetchone()
            if stored_row is not None:
                peer["first_message_at"] = stored_row["date"]
    return build_peer_coverage(
        peer,
        fetch=dict(fetch) if fetch is not None else None,
        media=dict(media) if media is not None else None,
        stats=stats,
    )


async def backfill_stored_media_kinds(conn: Any) -> None:
    """Rewrite ``messages.media.kind`` when mime/filename say image or video."""
    kind = _STORED_MEDIA_KIND_SQL.strip()
    await conn.execute(
        f"""
        UPDATE messages
        SET media = jsonb_set(media, '{{kind}}', to_jsonb(({kind})::text), true)
        WHERE media IS NOT NULL
          AND jsonb_typeof(media) = 'object'
          AND ({kind}) IS NOT NULL
          AND media->>'kind' IS DISTINCT FROM ({kind})
        """
    )
