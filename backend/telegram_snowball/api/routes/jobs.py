from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from psycopg.types.json import Jsonb

from telegram_snowball.api.routes.dialogues import load_public_peer
from telegram_snowball.config import load_settings
from telegram_snowball.db import get_conn
from telegram_snowball.models_health import EmbeddingGateError, assert_snowball_embed_gate
from telegram_snowball.telegram.ids import infer_peer_id_kind

router = APIRouter()

TaskType = Literal["fetch_dialogues", "forward_snowball"]


class CreateJobIn(BaseModel):
    task_type: TaskType
    params: dict[str, Any] = Field(default_factory=dict)


def _normalize_snowball_params(params: dict[str, Any]) -> dict[str, Any]:
    out = dict(params)
    out.setdefault("embed_images", True)
    out.setdefault("embed_text", True)
    out.setdefault("images", True)
    out.setdefault("videos", True)
    out.setdefault("messages", True)
    out.setdefault("participants", False)
    out.setdefault("restrict_date_range", False)
    out["embed_images"] = bool(out["embed_images"])
    out["embed_text"] = bool(out["embed_text"])
    return out


@router.get("/jobs")
async def list_jobs(limit: int = 50) -> dict[str, Any]:
    settings = load_settings()
    async with get_conn(settings) as conn:
        rows = await conn.execute(
            """
            SELECT id, task_type, status, params, progress, error,
                   created_at, started_at, finished_at
            FROM jobs
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (min(max(limit, 1), 200),),
        )
        items = await rows.fetchall()
    return {"jobs": [dict(row) for row in items]}


@router.get("/jobs/{job_id}")
async def get_job(job_id: UUID) -> dict[str, Any]:
    settings = load_settings()
    async with get_conn(settings) as conn:
        row = await conn.execute(
            """
            SELECT id, task_type, status, params, progress, error,
                   created_at, started_at, finished_at, heartbeat_at
            FROM jobs WHERE id = %s
            """,
            (job_id,),
        )
        job = await row.fetchone()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return dict(job)


@router.post("/jobs")
async def create_job(body: CreateJobIn) -> dict[str, Any]:
    settings = load_settings()
    params = dict(body.params)
    async with get_conn(settings) as conn:
        session = await conn.execute("SELECT id FROM telegram_sessions LIMIT 1")
        if await session.fetchone() is None:
            raise HTTPException(status_code=400, detail="Connect a Telegram account first.")
        running = await conn.execute(
            "SELECT id FROM jobs WHERE status IN ('queued', 'running') LIMIT 1"
        )
        if await running.fetchone():
            raise HTTPException(
                status_code=409,
                detail="A job is already queued or running. v1 runs one worker / one job at a time.",
            )

        if body.task_type == "fetch_dialogues":
            params.setdefault("mode", "materialize")
            params.setdefault("messages", False)
            params.setdefault("participants", False)

        if body.task_type == "forward_snowball":
            params = _normalize_snowball_params(params)
            if not params.get("seed_external_id"):
                raise HTTPException(status_code=400, detail="seed_external_id is required")
            try:
                assert_snowball_embed_gate(settings, params)
            except EmbeddingGateError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

        inserted = await conn.execute(
            """
            INSERT INTO jobs (task_type, status, params)
            VALUES (%s, 'queued', %s)
            RETURNING id, task_type, status, params, progress, created_at
            """,
            (body.task_type, Jsonb(params)),
        )
        job = await inserted.fetchone()
        await conn.commit()
    assert job is not None
    return dict(job)


class SeedResolveIn(BaseModel):
    query: str = Field(..., min_length=1)


@router.post("/snowball/resolve")
async def resolve_seed(body: SeedResolveIn) -> dict[str, Any]:
    """Resolve a seed by username or stored peer id, then materialize full + profile photo."""
    settings = load_settings()
    query = body.query.strip().lstrip("@")
    kind = infer_peer_id_kind(query)
    stored: dict[str, Any] | None = None
    async with get_conn(settings) as conn:
        if kind == "peer_id":
            row = await conn.execute(
                """
                SELECT external_id, username
                FROM peers WHERE external_id = %s
                """,
                (int(query),),
            )
            hit = await row.fetchone()
            if hit is None:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "That looks like a peer id, but it is not in this account's dialogues. "
                        "Telegram cannot look up a bare id. Wait for dialogues to finish loading, or use a username."
                    ),
                )
            stored = dict(hit)
        else:
            row = await conn.execute(
                """
                SELECT external_id, username
                FROM peers
                WHERE lower(username) = lower(%s)
                LIMIT 1
                """,
                (query,),
            )
            hit = await row.fetchone()
            if hit is not None:
                stored = dict(hit)

    from telethon.errors import (
        ChannelPrivateError,
        ChatForbiddenError,
        FloodWaitError,
        UsernameInvalidError,
        UsernameNotOccupiedError,
    )
    from telegram_snowball.telegram.client import telegram_client
    from telegram_snowball.telegram.materialize import materialize_peer

    if kind == "peer_id":
        assert stored is not None
        lookup: str | int = stored["username"] or stored["external_id"]
    else:
        lookup = query
    try:
        async with telegram_client(settings) as client:
            entity = await client.get_entity(lookup)
            async with get_conn(settings) as conn:
                signed = await materialize_peer(
                    client,
                    conn,
                    settings=settings,
                    entity=entity,
                    materialize_linked=False,
                )
                if signed is None:
                    raise HTTPException(status_code=400, detail="Resolved entity is not a usable peer")
                await conn.commit()
                peer = await load_public_peer(conn, signed, data_dir=settings.data_dir)
                if peer is None:
                    raise HTTPException(status_code=500, detail="Resolved peer could not be loaded")
    except HTTPException:
        raise
    except FloodWaitError as exc:
        raise HTTPException(
            status_code=429,
            detail=f"Telegram flood wait ({exc.seconds}s). Try again shortly.",
        ) from exc
    except (UsernameNotOccupiedError, UsernameInvalidError, ValueError, ChannelPrivateError, ChatForbiddenError) as exc:
        label = f"@{query}" if kind != "peer_id" else query
        raise HTTPException(status_code=404, detail=f"Could not resolve {label}: {exc}") from exc

    return {"peer": peer, "resolved": stored is None}
