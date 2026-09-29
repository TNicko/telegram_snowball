"""Load Scope params/inputs and persist image + peer scores."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import numpy as np

from telegram_snowball.embed.vectors import vector_literal
from telegram_snowball.scope.score import (
    ScopeParams,
    as_unit_vector,
    forward_score,
    mix_score,
    score_image,
)


def _params_from_row(row: dict[str, Any] | None) -> ScopeParams:
    if not row:
        return ScopeParams()
    return ScopeParams(
        tau=float(row.get("tau") or 0.4),
        gamma=float(row.get("gamma") or 2.0),
        alpha=float(row.get("alpha") or 2.0),
        delta=float(row.get("delta") or 0.15),
        lambda_fwd=float(row.get("lambda_fwd") or 0.05),
        version=int(row.get("version") or 0),
    )


async def ensure_state(conn: Any) -> ScopeParams:
    await conn.execute("INSERT INTO scope_state (id) VALUES (1) ON CONFLICT (id) DO NOTHING")
    row = await conn.execute(
        """
        SELECT tau, gamma, alpha, delta, lambda_fwd, version, last_rerank_at, updated_at
        FROM scope_state WHERE id = 1
        """
    )
    data = await row.fetchone()
    return _params_from_row(dict(data) if data else None)


async def load_params(conn: Any) -> ScopeParams:
    return await ensure_state(conn)


async def bump_version(conn: Any) -> int:
    await ensure_state(conn)
    row = await conn.execute(
        """
        UPDATE scope_state
        SET version = version + 1, updated_at = now()
        WHERE id = 1
        RETURNING version
        """
    )
    data = await row.fetchone()
    return int(data["version"]) if data else 1


async def mark_reranked(conn: Any, *, version: int) -> None:
    await conn.execute(
        """
        UPDATE scope_state
        SET version = %s, last_rerank_at = now(), updated_at = now()
        WHERE id = 1
        """,
        (version,),
    )


async def load_input_matrix(conn: Any) -> tuple[np.ndarray, list[str]]:
    rows = await conn.execute(
        """
        SELECT id, embedding::text AS embedding
        FROM scope_inputs
        WHERE embedding IS NOT NULL
        ORDER BY created_at ASC
        """
    )
    vectors: list[np.ndarray] = []
    ids: list[str] = []
    for row in await rows.fetchall():
        try:
            vectors.append(as_unit_vector(row["embedding"]))
        except ValueError:
            continue
        ids.append(str(row["id"]))
    if not vectors:
        return np.zeros((0, 0), dtype=np.float32), []
    return np.stack(vectors, axis=0), ids


def public_input(row: dict[str, Any]) -> dict[str, Any]:
    kind = str(row.get("kind") or "text")
    body = str(row.get("body") or "")
    return {
        "id": str(row["id"]),
        "kind": kind,
        "text": body if kind == "text" else None,
        "filename": row.get("filename"),
        "content_type": row.get("content_type"),
        "model_id": row.get("model_id"),
        "created_at": row.get("created_at"),
        "has_embedding": row.get("embedding") is not None or row.get("has_embedding"),
    }


async def list_inputs(conn: Any) -> list[dict[str, Any]]:
    rows = await conn.execute(
        """
        SELECT id, kind, body, filename, content_type, model_id, dim,
               embedding IS NOT NULL AS has_embedding, created_at
        FROM scope_inputs
        ORDER BY created_at ASC
        """
    )
    return [public_input(dict(row)) for row in await rows.fetchall()]


async def insert_input(
    conn: Any,
    *,
    kind: str,
    body: str,
    filename: str | None,
    content_type: str | None,
    values: Any,
    model_id: str,
    dim: int,
) -> dict[str, Any]:
    lit = vector_literal(values)
    row = await conn.execute(
        """
        INSERT INTO scope_inputs (kind, body, filename, content_type, embedding, model_id, dim)
        VALUES (%s, %s, %s, %s, %s::vector, %s, %s)
        RETURNING id, kind, body, filename, content_type, model_id, dim,
                  true AS has_embedding, created_at
        """,
        (kind, body, filename, content_type, lit, model_id, dim),
    )
    data = await row.fetchone()
    assert data is not None
    await bump_version(conn)
    return public_input(dict(data))


async def delete_input(conn: Any, input_id: UUID) -> dict[str, Any] | None:
    row = await conn.execute(
        """
        DELETE FROM scope_inputs
        WHERE id = %s
        RETURNING id, kind, body, filename, content_type, model_id, dim,
                  true AS has_embedding, created_at
        """,
        (input_id,),
    )
    data = await row.fetchone()
    if data is None:
        return None
    await bump_version(conn)
    return public_input(dict(data))


async def get_input(conn: Any, input_id: UUID) -> dict[str, Any] | None:
    row = await conn.execute(
        "SELECT id, kind, body, filename, content_type FROM scope_inputs WHERE id = %s",
        (input_id,),
    )
    data = await row.fetchone()
    return dict(data) if data else None


async def load_forward_scores(conn: Any, peer_ids: list[int]) -> dict[int, float]:
    if not peer_ids:
        return {}
    rows = await conn.execute(
        """
        SELECT external_id, COALESCE(forward_score, 0)::float8 AS forward_score
        FROM peers
        WHERE external_id = ANY(%s)
        """,
        (peer_ids,),
    )
    return {int(row["external_id"]): float(row["forward_score"]) for row in await rows.fetchall()}


def score_rows(
    embeddings: list[tuple[str, np.ndarray]],
    inputs: np.ndarray,
    params: ScopeParams,
) -> list[tuple[str, float, float]]:
    out: list[tuple[str, float, float]] = []
    for phash, vector in embeddings:
        s, r = score_image(vector, inputs, params)
        out.append((phash, s, r))
    return out


async def upsert_image_scores(
    conn: Any,
    rows: list[tuple[str, float, float]],
    *,
    version: int,
) -> None:
    for phash, s, r in rows:
        await conn.execute(
            """
            INSERT INTO image_scope_scores (phash, s, r, version, updated_at)
            VALUES (%s, %s, %s, %s, now())
            ON CONFLICT (phash) DO UPDATE SET
                s = EXCLUDED.s,
                r = EXCLUDED.r,
                version = EXCLUDED.version,
                updated_at = now()
            """,
            (phash, s, r, version),
        )


async def recompute_peer_scores(conn: Any, peer_ids: list[int], params: ScopeParams) -> None:
    if not peer_ids:
        return
    await conn.execute(
        """
        UPDATE peers SET
            scope_score = COALESCE(
                scope_r / NULLIF(scope_r + %s + %s * scope_j, 0),
                0
            ),
            forward_score = COALESCE(
                forward_r / NULLIF(forward_r + %s + %s * forward_j, 0),
                0
            ) + %s * LN(1.0 + GREATEST(forward_n_events, 0)),
            updated_at = now()
        WHERE external_id = ANY(%s)
        """,
        (params.alpha, params.delta, params.alpha, params.delta, params.lambda_fwd, peer_ids),
    )


async def apply_unique_phashes(
    conn: Any,
    *,
    peer_id: int,
    pile: str,
    scored: dict[str, float],
) -> tuple[float, int]:
    """Credit new unique phashes onto a pile. Returns (delta_R, delta_J)."""
    if pile not in {"scope", "forward"}:
        raise ValueError(f"unknown pile={pile}")
    if not scored:
        return 0.0, 0
    phashes = list(scored.keys())
    inserted = await conn.execute(
        """
        INSERT INTO peer_scope_evidence (peer_external_id, pile, phash)
        SELECT %s, %s, x
        FROM UNNEST(%s::text[]) AS x
        ON CONFLICT DO NOTHING
        RETURNING phash
        """,
        (peer_id, pile, phashes),
    )
    new_phashes = [str(row["phash"]) for row in await inserted.fetchall()]
    if not new_phashes:
        return 0.0, 0
    delta_r = sum(float(scored.get(phash, 0.0)) for phash in new_phashes)
    delta_j = len(new_phashes)
    column_r = "scope_r" if pile == "scope" else "forward_r"
    column_j = "scope_j" if pile == "scope" else "forward_j"
    await conn.execute(
        f"""
        UPDATE peers SET
            {column_r} = {column_r} + %s,
            {column_j} = {column_j} + %s,
            updated_at = now()
        WHERE external_id = %s
        """,
        (delta_r, delta_j, peer_id),
    )
    return delta_r, delta_j


async def apply_forward_events(
    conn: Any,
    occurrences: list[tuple[int, Any, str]],
) -> dict[int, int]:
    """Insert new forwarded-image events. Returns origin → new event count."""
    added: dict[int, int] = {}
    for origin_id, message_id, phash in occurrences:
        row = await conn.execute(
            """
            INSERT INTO peer_scope_forward_events (origin_peer_id, message_id, phash)
            VALUES (%s, %s, %s)
            ON CONFLICT DO NOTHING
            RETURNING origin_peer_id
            """,
            (origin_id, message_id, phash),
        )
        data = await row.fetchone()
        if data is None:
            continue
        added[origin_id] = added.get(origin_id, 0) + 1
    for origin_id, n in added.items():
        await conn.execute(
            """
            UPDATE peers SET
                forward_n_events = forward_n_events + %s,
                updated_at = now()
            WHERE external_id = %s
            """,
            (n, origin_id),
        )
    return added


def peer_mix(r_sum: float, unique_n: int, events: int, params: ScopeParams) -> tuple[float, float]:
    mix = mix_score(r_sum, unique_n, params)
    return mix, forward_score(mix, events, params)
