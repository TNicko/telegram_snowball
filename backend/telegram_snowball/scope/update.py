"""Score a peer's unique images after they have been embedded."""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

from telegram_snowball.scope.score import ScopeParams, as_unit_vector, score_image
from telegram_snowball.scope.store import (
    apply_forward_events,
    apply_unique_phashes,
    load_input_matrix,
    load_params,
    recompute_peer_scores,
    upsert_image_scores,
)

lg = logging.getLogger(__name__)


async def _embeddings_for_phashes(conn: Any, phashes: list[str]) -> list[tuple[str, np.ndarray]]:
    if not phashes:
        return []
    rows = await conn.execute(
        """
        SELECT phash, embedding::text AS embedding
        FROM image_embeddings
        WHERE phash = ANY(%s)
        """,
        (phashes,),
    )
    out: list[tuple[str, np.ndarray]] = []
    for row in await rows.fetchall():
        try:
            out.append((str(row["phash"]), as_unit_vector(row["embedding"])))
        except ValueError:
            continue
    return out


async def _score_phashes(
    conn: Any,
    phashes: list[str],
    inputs: np.ndarray,
    params: ScopeParams,
) -> dict[str, float]:
    embeddings = await _embeddings_for_phashes(conn, phashes)
    rows: list[tuple[str, float, float]] = []
    scored: dict[str, float] = {}
    for phash, vector in embeddings:
        s, r = score_image(vector, inputs, params)
        rows.append((phash, s, r))
        scored[phash] = r
    await upsert_image_scores(conn, rows, version=params.version)
    return scored


async def score_after_peer_embed(conn: Any, *, peer_external_id: int) -> dict[str, int]:
    """Update scrape + forward scores from unique images on ``peer_external_id``."""
    params = await load_params(conn)
    inputs, _ids = await load_input_matrix(conn)
    if inputs.size == 0:
        return {"images": 0, "origins": 0}

    own = await conn.execute(
        """
        SELECT DISTINCT ibm.phash
        FROM image_blob_messages ibm
        JOIN image_embeddings e ON e.phash = ibm.phash
        WHERE ibm.peer_external_id = %s
        """,
        (peer_external_id,),
    )
    own_phashes = [str(row["phash"]) for row in await own.fetchall()]
    own_scored = await _score_phashes(conn, own_phashes, inputs, params)
    await apply_unique_phashes(
        conn, peer_id=peer_external_id, pile="scope", scored=own_scored
    )

    fwd = await conn.execute(
        """
        SELECT fem.to_external_id AS origin_id, fem.message_id, ibm.phash
        FROM forward_edge_messages fem
        JOIN image_blob_messages ibm ON ibm.message_id = fem.message_id
        JOIN image_embeddings e ON e.phash = ibm.phash
        JOIN peers p ON p.external_id = fem.to_external_id
        WHERE fem.from_external_id = %s
        """,
        (peer_external_id,),
    )
    occurrences: list[tuple[int, Any, str]] = []
    origin_phashes: dict[int, set[str]] = {}
    extra_phashes: set[str] = set()
    for row in await fwd.fetchall():
        origin_id = int(row["origin_id"])
        phash = str(row["phash"])
        occurrences.append((origin_id, row["message_id"], phash))
        origin_phashes.setdefault(origin_id, set()).add(phash)
        if phash not in own_scored:
            extra_phashes.add(phash)

    extra_scored = await _score_phashes(conn, list(extra_phashes), inputs, params)
    scored = {**own_scored, **extra_scored}
    touched = {peer_external_id}
    for origin_id, phashes in origin_phashes.items():
        subset = {phash: scored[phash] for phash in phashes if phash in scored}
        await apply_unique_phashes(conn, peer_id=origin_id, pile="forward", scored=subset)
        touched.add(origin_id)
    await apply_forward_events(conn, occurrences)
    await recompute_peer_scores(conn, list(touched), params)
    return {"images": len(own_scored), "origins": len(origin_phashes)}
