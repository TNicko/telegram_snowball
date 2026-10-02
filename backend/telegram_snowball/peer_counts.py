"""Stored per-peer totals. Callers add to these when they insert; nothing recounts messages."""

from __future__ import annotations

from typing import Any

_MEDIA_KINDS = ("image", "video", "audio", "gif", "document")

COUNT_COLUMNS = (
    "posts",
    "text_total",
    "text_embedded",
    "image_total",
    "image_hashed",
    "image_downloaded",
    "image_unique",
    "image_persisted",
    "image_embeddable",
    "image_embedded_unique",
    "video_total",
    "video_downloaded",
    "audio_total",
    "audio_downloaded",
    "gif_total",
    "gif_downloaded",
    "document_total",
    "document_downloaded",
    "unique_forwards",
    "total_forwards",
)
_COUNT_COLUMN_SET = frozenset(COUNT_COLUMNS)
_PHASH_FIELDS = (
    "image_unique",
    "image_persisted",
    "image_embeddable",
    "image_embedded_unique",
)


def empty_count_row() -> dict[str, int]:
    return {column: 0 for column in COUNT_COLUMNS}


def stats_from_counts(row: dict[str, Any] | None) -> dict[str, int]:
    stats = empty_count_row()
    if not row:
        return stats
    for column in COUNT_COLUMNS:
        stats[column] = int(row.get(column) or 0)
    return stats


async def bump_peer_counts(conn: Any, peer_id: int, deltas: dict[str, int]) -> None:
    clean = {
        column: int(amount)
        for column, amount in deltas.items()
        if column in _COUNT_COLUMN_SET and int(amount)
    }
    if not clean:
        return
    columns = list(clean)
    insert_cols = ", ".join(["peer_external_id", *columns])
    placeholders = ", ".join(["%s"] * (1 + len(columns)))
    assignments = ", ".join(
        f"{column} = GREATEST(peer_counts.{column} + %s, 0)" for column in columns
    )
    amounts = [clean[column] for column in columns]
    await conn.execute(
        f"""
        INSERT INTO peer_counts ({insert_cols})
        VALUES ({placeholders})
        ON CONFLICT (peer_external_id) DO UPDATE SET {assignments}
        """,
        (peer_id, *[max(amount, 0) for amount in amounts], *amounts),
    )


async def load_peer_count_map(conn: Any) -> dict[int, dict[str, int]]:
    rows = await conn.execute("SELECT * FROM peer_counts")
    return {
        int(row["peer_external_id"]): stats_from_counts(row) for row in await rows.fetchall()
    }


async def load_peer_count(conn: Any, peer_id: int) -> dict[str, int]:
    row = await conn.execute(
        "SELECT * FROM peer_counts WHERE peer_external_id = %s",
        (peer_id,),
    )
    return stats_from_counts(await row.fetchone())


def message_insert_deltas(
    *,
    content: str | None,
    kind: str,
    downloaded: bool,
) -> dict[str, int]:
    deltas = {"posts": 1}
    if content and str(content).strip():
        deltas["text_total"] = 1
    if kind in _MEDIA_KINDS:
        deltas[f"{kind}_total"] = 1
        if downloaded:
            deltas[f"{kind}_downloaded"] = 1
    return deltas


async def phash_peer_snapshot(conn: Any, phash: str) -> dict[int, tuple[int, int, int, int]]:
    blob = await conn.execute(
        """
        SELECT
            NULLIF(BTRIM(canonical_path), '') IS NOT NULL AS persisted,
            image_embedded,
            EXISTS (SELECT 1 FROM image_cache c WHERE c.phash = image_blobs.phash) AS cached
        FROM image_blobs
        WHERE phash = %s
        """,
        (phash,),
    )
    found = await blob.fetchone()
    if found is None:
        return {}
    persisted = bool(found["persisted"])
    embedded = bool(found["image_embedded"])
    embeddable = embedded or persisted or bool(found["cached"])
    peers = await conn.execute(
        """
        SELECT DISTINCT peer_external_id
        FROM image_blob_messages
        WHERE phash = %s AND peer_external_id IS NOT NULL
        """,
        (phash,),
    )
    flag = (
        1,
        1 if persisted else 0,
        1 if embeddable else 0,
        1 if embedded else 0,
    )
    return {int(row["peer_external_id"]): flag for row in await peers.fetchall()}


async def apply_phash_snapshot(
    conn: Any,
    phash: str,
    before: dict[int, tuple[int, int, int, int]],
) -> None:
    after = await phash_peer_snapshot(conn, phash)
    for peer_id in set(before) | set(after):
        previous = before.get(peer_id, (0, 0, 0, 0))
        current = after.get(peer_id, (0, 0, 0, 0))
        deltas = {
            column: current[index] - previous[index]
            for index, column in enumerate(_PHASH_FIELDS)
            if current[index] != previous[index]
        }
        await bump_peer_counts(conn, peer_id, deltas)


async def backfill_peer_counts(conn: Any) -> None:
    """Fill peer_counts once from the tables that already exist. Later writes only increment."""
    await conn.execute("SELECT pg_advisory_xact_lock(%s)", (814_201,))
    flag = await conn.execute("SELECT 1 FROM app_settings WHERE key = 'peer_counts_v1'")
    if await flag.fetchone() is not None:
        return
    from telegram_snowball.catalog import _IMAGE_HAS_PHASH_SQL, _STORED_MEDIA_KIND_SQL

    kind = _STORED_MEDIA_KIND_SQL.strip()
    columns = ", ".join(COUNT_COLUMNS)
    await conn.execute(
        f"""
        INSERT INTO peer_counts (peer_external_id, {columns})
        SELECT
            ids.peer_external_id,
            COALESCE(m.posts, 0),
            COALESCE(m.text_total, 0),
            COALESCE(m.text_embedded, 0),
            COALESCE(m.image_total, 0),
            COALESCE(m.image_hashed, 0),
            COALESCE(m.image_downloaded, 0),
            COALESCE(b.image_unique, 0),
            COALESCE(b.image_persisted, 0),
            COALESCE(b.image_embeddable, 0),
            COALESCE(b.image_embedded_unique, 0),
            COALESCE(m.video_total, 0),
            COALESCE(m.video_downloaded, 0),
            COALESCE(m.audio_total, 0),
            COALESCE(m.audio_downloaded, 0),
            COALESCE(m.gif_total, 0),
            COALESCE(m.gif_downloaded, 0),
            COALESCE(m.document_total, 0),
            COALESCE(m.document_downloaded, 0),
            COALESCE(f.unique_forwards, 0),
            COALESCE(f.total_forwards, 0)
        FROM (
            SELECT peer_external_id FROM messages
            UNION
            SELECT peer_external_id FROM image_blob_messages WHERE peer_external_id IS NOT NULL
            UNION
            SELECT from_external_id AS peer_external_id FROM forward_edges
        ) ids
        LEFT JOIN (
            SELECT
                peer_external_id,
                COUNT(*)::int AS posts,
                COUNT(*) FILTER (WHERE NULLIF(BTRIM(content), '') IS NOT NULL)::int AS text_total,
                COUNT(*) FILTER (
                    WHERE NULLIF(BTRIM(content), '') IS NOT NULL AND text_embedded
                )::int AS text_embedded,
                COUNT(*) FILTER (WHERE ({kind}) = 'image')::int AS image_total,
                COUNT(*) FILTER (
                    WHERE ({kind}) = 'image' AND {_IMAGE_HAS_PHASH_SQL}
                )::int AS image_hashed,
                COUNT(*) FILTER (
                    WHERE ({kind}) = 'image' AND media->>'downloaded' IN ('true', 't', '1')
                )::int AS image_downloaded,
                COUNT(*) FILTER (WHERE ({kind}) = 'video')::int AS video_total,
                COUNT(*) FILTER (
                    WHERE ({kind}) = 'video' AND media->>'downloaded' IN ('true', 't', '1')
                )::int AS video_downloaded,
                COUNT(*) FILTER (WHERE ({kind}) = 'audio')::int AS audio_total,
                COUNT(*) FILTER (
                    WHERE ({kind}) = 'audio' AND media->>'downloaded' IN ('true', 't', '1')
                )::int AS audio_downloaded,
                COUNT(*) FILTER (WHERE ({kind}) = 'gif')::int AS gif_total,
                COUNT(*) FILTER (
                    WHERE ({kind}) = 'gif' AND media->>'downloaded' IN ('true', 't', '1')
                )::int AS gif_downloaded,
                COUNT(*) FILTER (WHERE ({kind}) = 'document')::int AS document_total,
                COUNT(*) FILTER (
                    WHERE ({kind}) = 'document' AND media->>'downloaded' IN ('true', 't', '1')
                )::int AS document_downloaded
            FROM messages
            GROUP BY peer_external_id
        ) m ON m.peer_external_id = ids.peer_external_id
        LEFT JOIN (
            SELECT
                ibm.peer_external_id,
                COUNT(DISTINCT ibm.phash)::int AS image_unique,
                COUNT(DISTINCT ibm.phash) FILTER (
                    WHERE NULLIF(b.canonical_path, '') IS NOT NULL
                )::int AS image_persisted,
                COUNT(DISTINCT ibm.phash) FILTER (
                    WHERE b.image_embedded
                       OR NULLIF(BTRIM(b.canonical_path), '') IS NOT NULL
                       OR EXISTS (SELECT 1 FROM image_cache c WHERE c.phash = b.phash)
                )::int AS image_embeddable,
                COUNT(DISTINCT ibm.phash) FILTER (WHERE b.image_embedded)::int AS image_embedded_unique
            FROM image_blob_messages ibm
            JOIN image_blobs b ON b.phash = ibm.phash
            GROUP BY ibm.peer_external_id
        ) b ON b.peer_external_id = ids.peer_external_id
        LEFT JOIN (
            SELECT
                from_external_id AS peer_external_id,
                COUNT(*)::int AS unique_forwards,
                COALESCE(SUM(forward_count), 0)::int AS total_forwards
            FROM forward_edges
            GROUP BY from_external_id
        ) f ON f.peer_external_id = ids.peer_external_id
        ON CONFLICT (peer_external_id) DO UPDATE SET
            {", ".join(f"{column} = EXCLUDED.{column}" for column in COUNT_COLUMNS)}
        """
    )
    await conn.execute(
        "INSERT INTO app_settings (key, value) VALUES ('peer_counts_v1', 'true'::jsonb)"
    )
