"""Rebuild Scope scores from stored vision embeddings (no re-encode)."""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from telegram_snowball.config import Settings
from telegram_snowball.jobs.progress import raise_if_cancelled, update_job_progress
from telegram_snowball.scope.score import as_unit_vector, score_image
from telegram_snowball.scope.store import (
    load_input_matrix,
    load_params,
    mark_reranked,
    recompute_peer_scores,
    upsert_image_scores,
)

lg = logging.getLogger(__name__)

BATCH = 2000


async def _zero_peer_scores(conn: Any) -> None:
    await conn.execute("DELETE FROM peer_scope_evidence")
    await conn.execute("DELETE FROM peer_scope_forward_events")
    await conn.execute("DELETE FROM image_scope_scores")
    await conn.execute(
        """
        UPDATE peers SET
            scope_r = 0, scope_j = 0, scope_score = 0,
            forward_r = 0, forward_j = 0, forward_n_events = 0, forward_score = 0
        WHERE scope_r <> 0 OR scope_j <> 0 OR scope_score <> 0
           OR forward_r <> 0 OR forward_j <> 0 OR forward_n_events <> 0
           OR forward_score <> 0
        """
    )


async def run_scope_rerank(
    conn: Any,
    *,
    settings: Settings,
    job_id: UUID,
    params: dict[str, Any],
) -> None:
    del settings, params
    cfg = await load_params(conn)
    inputs, _ids = await load_input_matrix(conn)
    await update_job_progress(
        conn,
        job_id,
        {"phase": "scope_rerank", "detail": "Scoring unique images", "version": cfg.version},
    )
    await _zero_peer_scores(conn)
    await conn.commit()
    if inputs.size == 0:
        version = cfg.version
        await mark_reranked(conn, version=version)
        await update_job_progress(
            conn,
            job_id,
            {
                "phase": "done",
                "detail": "No Scope inputs; scores cleared",
                "images_scored": 0,
                "version": version,
            },
        )
        return

    scored_n = 0
    offset = 0
    while True:
        await raise_if_cancelled(conn, job_id)
        rows = await conn.execute(
            """
            SELECT phash, embedding::text AS embedding
            FROM image_embeddings
            ORDER BY phash
            LIMIT %s OFFSET %s
            """,
            (BATCH, offset),
        )
        batch = await rows.fetchall()
        if not batch:
            break
        scored: list[tuple[str, float, float]] = []
        for row in batch:
            try:
                vector = as_unit_vector(row["embedding"])
            except ValueError:
                continue
            s, r = score_image(vector, inputs, cfg)
            scored.append((str(row["phash"]), s, r))
        await upsert_image_scores(conn, scored, version=cfg.version)
        scored_n += len(scored)
        offset += len(batch)
        await conn.commit()
        await update_job_progress(
            conn,
            job_id,
            {
                "phase": "scope_rerank",
                "detail": f"Scored {scored_n} images",
                "images_scored": scored_n,
            },
        )

    await raise_if_cancelled(conn, job_id)
    await update_job_progress(
        conn, job_id, {"phase": "scope_rerank", "detail": "Updating scrape scores"}
    )
    await conn.execute(
        """
        INSERT INTO peer_scope_evidence (peer_external_id, pile, phash)
        SELECT DISTINCT ibm.peer_external_id, 'scope', ibm.phash
        FROM image_blob_messages ibm
        JOIN image_scope_scores s ON s.phash = ibm.phash
        ON CONFLICT DO NOTHING
        """
    )
    await conn.execute(
        """
        INSERT INTO peer_scope_evidence (peer_external_id, pile, phash)
        SELECT DISTINCT fem.to_external_id, 'forward', ibm.phash
        FROM forward_edge_messages fem
        JOIN image_blob_messages ibm ON ibm.message_id = fem.message_id
        JOIN image_scope_scores s ON s.phash = ibm.phash
        JOIN peers p ON p.external_id = fem.to_external_id
        ON CONFLICT DO NOTHING
        """
    )
    await conn.execute(
        """
        INSERT INTO peer_scope_forward_events (origin_peer_id, message_id, phash)
        SELECT fem.to_external_id, fem.message_id, ibm.phash
        FROM forward_edge_messages fem
        JOIN image_blob_messages ibm ON ibm.message_id = fem.message_id
        JOIN image_scope_scores s ON s.phash = ibm.phash
        JOIN peers p ON p.external_id = fem.to_external_id
        ON CONFLICT DO NOTHING
        """
    )
    await conn.execute(
        """
        UPDATE peers p SET
            scope_r = COALESCE(x.r_sum, 0),
            scope_j = COALESCE(x.j, 0)
        FROM (
            SELECT e.peer_external_id AS id,
                   SUM(s.r)::float8 AS r_sum,
                   COUNT(*)::int AS j
            FROM peer_scope_evidence e
            JOIN image_scope_scores s ON s.phash = e.phash
            WHERE e.pile = 'scope'
            GROUP BY e.peer_external_id
        ) x
        WHERE p.external_id = x.id
        """
    )
    await conn.execute(
        """
        UPDATE peers p SET
            forward_r = COALESCE(x.r_sum, 0),
            forward_j = COALESCE(x.j, 0)
        FROM (
            SELECT e.peer_external_id AS id,
                   SUM(s.r)::float8 AS r_sum,
                   COUNT(*)::int AS j
            FROM peer_scope_evidence e
            JOIN image_scope_scores s ON s.phash = e.phash
            WHERE e.pile = 'forward'
            GROUP BY e.peer_external_id
        ) x
        WHERE p.external_id = x.id
        """
    )
    await conn.execute(
        """
        UPDATE peers p SET
            forward_n_events = COALESCE(x.n, 0)
        FROM (
            SELECT origin_peer_id AS id, COUNT(*)::int AS n
            FROM peer_scope_forward_events
            GROUP BY origin_peer_id
        ) x
        WHERE p.external_id = x.id
        """
    )
    ids = await conn.execute(
        """
        SELECT external_id FROM peers
        WHERE scope_j <> 0 OR forward_j <> 0 OR forward_n_events <> 0
        """
    )
    peer_ids = [int(row["external_id"]) for row in await ids.fetchall()]
    await recompute_peer_scores(conn, peer_ids, cfg)
    await mark_reranked(conn, version=cfg.version)
    await conn.commit()
    await update_job_progress(
        conn,
        job_id,
        {
            "phase": "done",
            "detail": f"Rescored {scored_n} images · {len(peer_ids)} peers",
            "images_scored": scored_n,
            "peers_updated": len(peer_ids),
            "version": cfg.version,
        },
    )
    lg.info("scope rerank scored=%s peers=%s version=%s", scored_n, len(peer_ids), cfg.version)
