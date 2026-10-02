"""Read and write embedding rows, then nearest-neighbor search."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from telegram_snowball.embed.vectors import vector_literal
from telegram_snowball.phash import is_dedupable_phash, normalize_phash_hex


def _vec(values: Any) -> str:
    return vector_literal(values)


async def upsert_text_embedding(
    conn: Any,
    *,
    message_id: UUID | str,
    model_id: str,
    values: Any,
) -> None:
    lit = _vec(values)
    dim = int(len(values))
    await conn.execute(
        """
        INSERT INTO message_text_embeddings (message_id, model_id, dim, embedding)
        VALUES (%s, %s, %s, %s::vector)
        ON CONFLICT (message_id) DO UPDATE SET
            model_id = EXCLUDED.model_id,
            dim = EXCLUDED.dim,
            embedding = EXCLUDED.embedding
        """,
        (message_id, model_id, dim, lit),
    )
    flipped = await conn.execute(
        """
        UPDATE messages
        SET text_embedded = true
        WHERE id = %s AND text_embedded = false
        RETURNING peer_external_id
        """,
        (message_id,),
    )
    row = await flipped.fetchone()
    if row is not None and row["peer_external_id"] is not None:
        from telegram_snowball.peer_counts import bump_peer_counts

        await bump_peer_counts(conn, int(row["peer_external_id"]), {"text_embedded": 1})


async def upsert_image_embedding(
    conn: Any,
    *,
    phash: str,
    model_id: str,
    values: Any,
) -> None:
    normalized = normalize_phash_hex(phash)
    if not is_dedupable_phash(normalized):
        return
    from telegram_snowball.peer_counts import apply_phash_snapshot, phash_peer_snapshot

    before = await phash_peer_snapshot(conn, normalized)
    lit = _vec(values)
    dim = int(len(values))
    await conn.execute(
        """
        INSERT INTO image_embeddings (phash, model_id, dim, embedding)
        VALUES (%s, %s, %s, %s::vector)
        ON CONFLICT (phash) DO UPDATE SET
            model_id = EXCLUDED.model_id,
            dim = EXCLUDED.dim,
            embedding = EXCLUDED.embedding
        """,
        (normalized, model_id, dim, lit),
    )
    await conn.execute(
        "UPDATE image_blobs SET image_embedded = true, updated_at = now() WHERE phash = %s",
        (normalized,),
    )
    await conn.execute(
        """
        UPDATE messages
        SET image_embedded = true
        WHERE id IN (SELECT message_id FROM image_blob_messages WHERE phash = %s)
        """,
        (normalized,),
    )
    await apply_phash_snapshot(conn, normalized, before)


async def reset_text_embeddings(conn: Any) -> None:
    await conn.execute("DELETE FROM message_text_embeddings")
    await conn.execute("UPDATE messages SET text_embedded = false")
    await conn.execute("UPDATE peer_counts SET text_embedded = 0")


async def reset_image_embeddings(conn: Any) -> None:
    await conn.execute("DELETE FROM image_embeddings")
    await conn.execute("UPDATE image_blobs SET image_embedded = false")
    await conn.execute("UPDATE messages SET image_embedded = false")
    await conn.execute(
        """
        UPDATE peer_counts pc
        SET image_embedded_unique = 0,
            image_embeddable = COALESCE((
                SELECT COUNT(DISTINCT ibm.phash)::int
                FROM image_blob_messages ibm
                JOIN image_blobs b ON b.phash = ibm.phash
                WHERE ibm.peer_external_id = pc.peer_external_id
                  AND (
                    NULLIF(BTRIM(b.canonical_path), '') IS NOT NULL
                    OR EXISTS (SELECT 1 FROM image_cache c WHERE c.phash = b.phash)
                  )
            ), 0)
        """
    )


async def pending_text_rows(
    conn: Any,
    *,
    peer_external_id: int | None,
    model_id: str,
    limit: int,
) -> list[dict[str, Any]]:
    if peer_external_id is None:
        rows = await conn.execute(
            """
            SELECT m.id, m.content
            FROM messages m
            LEFT JOIN message_text_embeddings e ON e.message_id = m.id
            WHERE NULLIF(BTRIM(m.content), '') IS NOT NULL
              AND (e.message_id IS NULL OR e.model_id IS DISTINCT FROM %s)
            ORDER BY m.date DESC
            LIMIT %s
            """,
            (model_id, limit),
        )
    else:
        rows = await conn.execute(
            """
            SELECT m.id, m.content
            FROM messages m
            LEFT JOIN message_text_embeddings e ON e.message_id = m.id
            WHERE m.peer_external_id = %s
              AND NULLIF(BTRIM(m.content), '') IS NOT NULL
              AND (e.message_id IS NULL OR e.model_id IS DISTINCT FROM %s)
            ORDER BY m.date DESC
            LIMIT %s
            """,
            (peer_external_id, model_id, limit),
        )
    return [dict(row) for row in await rows.fetchall()]


_HAS_PIXELS_SQL = """
(
  (
    NULLIF(BTRIM(b.canonical_path), '') IS NOT NULL
    AND POSITION('://' IN b.canonical_path) = 0
  )
  OR EXISTS (SELECT 1 FROM image_cache c WHERE c.phash = b.phash)
)
"""


async def pending_image_phashes(
    conn: Any,
    *,
    peer_external_id: int | None,
    model_id: str,
    limit: int,
    exclude: list[str] | None = None,
) -> list[str]:
    skip = [item for item in (exclude or []) if item] or [""]
    if peer_external_id is None:
        rows = await conn.execute(
            f"""
            SELECT b.phash
            FROM image_blobs b
            LEFT JOIN image_embeddings e ON e.phash = b.phash
            WHERE (e.phash IS NULL OR e.model_id IS DISTINCT FROM %s)
              AND {_HAS_PIXELS_SQL}
              AND NOT (b.phash = ANY(%s))
            ORDER BY b.updated_at DESC
            LIMIT %s
            """,
            (model_id, skip, limit),
        )
    else:
        rows = await conn.execute(
            f"""
            SELECT DISTINCT b.phash
            FROM image_blobs b
            JOIN image_blob_messages ibm ON ibm.phash = b.phash
            LEFT JOIN image_embeddings e ON e.phash = b.phash
            WHERE ibm.peer_external_id = %s
              AND (e.phash IS NULL OR e.model_id IS DISTINCT FROM %s)
              AND {_HAS_PIXELS_SQL}
              AND NOT (b.phash = ANY(%s))
            ORDER BY b.phash
            LIMIT %s
            """,
            (peer_external_id, model_id, skip, limit),
        )
    out: list[str] = []
    for row in await rows.fetchall():
        phash = str(row["phash"])
        if is_dedupable_phash(phash):
            out.append(phash)
    return out


async def search_text_messages(
    conn: Any,
    *,
    model_id: str,
    query: Any,
    limit: int,
    peer_external_id: int | None = None,
) -> list[dict[str, Any]]:
    lit = _vec(query)
    if peer_external_id is None:
        rows = await conn.execute(
            """
            SELECT e.message_id, (1 - (e.embedding <=> %s::vector))::float8 AS score
            FROM message_text_embeddings e
            WHERE e.model_id = %s
            ORDER BY e.embedding <=> %s::vector
            LIMIT %s
            """,
            (lit, model_id, lit, limit),
        )
    else:
        rows = await conn.execute(
            """
            SELECT e.message_id, (1 - (e.embedding <=> %s::vector))::float8 AS score
            FROM message_text_embeddings e
            JOIN messages m ON m.id = e.message_id
            WHERE e.model_id = %s AND m.peer_external_id = %s
            ORDER BY e.embedding <=> %s::vector
            LIMIT %s
            """,
            (lit, model_id, peer_external_id, lit, limit),
        )
    return [dict(row) for row in await rows.fetchall()]


async def search_image_blobs(
    conn: Any,
    *,
    model_id: str,
    query: Any,
    limit: int,
    peer_external_id: int | None = None,
) -> list[dict[str, Any]]:
    lit = _vec(query)
    if peer_external_id is None:
        rows = await conn.execute(
            """
            SELECT e.phash, (1 - (e.embedding <=> %s::vector))::float8 AS score
            FROM image_embeddings e
            WHERE e.model_id = %s
            ORDER BY e.embedding <=> %s::vector
            LIMIT %s
            """,
            (lit, model_id, lit, limit),
        )
    else:
        rows = await conn.execute(
            """
            SELECT e.phash, (1 - (e.embedding <=> %s::vector))::float8 AS score
            FROM image_embeddings e
            WHERE e.model_id = %s
              AND EXISTS (
                SELECT 1 FROM image_blob_messages ibm
                WHERE ibm.phash = e.phash AND ibm.peer_external_id = %s
              )
            ORDER BY e.embedding <=> %s::vector
            LIMIT %s
            """,
            (lit, model_id, peer_external_id, lit, limit),
        )
    return [dict(row) for row in await rows.fetchall()]
