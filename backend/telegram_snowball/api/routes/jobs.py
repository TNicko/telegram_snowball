from __future__ import annotations

import logging
from typing import Any, Literal
from uuid import UUID

import psycopg
from fastapi import APIRouter, HTTPException
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field

from telegram_snowball.api.routes.dialogues import PUBLIC_PEER_COLUMNS, load_public_peer, public_peer
from telegram_snowball.catalog import stored_kind_is
from telegram_snowball.config import load_settings
from telegram_snowball.db import get_conn
from telegram_snowball.jobs.lanes import lane_for, live_conflict_detail, live_job_in_lane
from telegram_snowball.jsonutil import json_safe
from telegram_snowball.models_health import EmbeddingGateError, assert_snowball_embed_gate
from telegram_snowball.telegram.ids import infer_peer_id_kind

router = APIRouter()
lg = logging.getLogger(__name__)

TaskType = Literal["fetch_dialogues", "forward_snowball", "embed", "scope_rerank"]


class CreateJobIn(BaseModel):
    task_type: TaskType
    params: dict[str, Any] = Field(default_factory=dict)


def _normalize_snowball_params(params: dict[str, Any]) -> dict[str, Any]:
    out = dict(params)
    out.setdefault("embed_images", True)
    out.setdefault("embed_text", True)
    out.setdefault("images", False)
    out.setdefault("videos", False)
    out.setdefault("messages", True)
    out.setdefault("participants", False)
    out.setdefault("restrict_date_range", False)
    out.setdefault("use_scope", False)
    out["embed_images"] = bool(out["embed_images"])
    out["embed_text"] = bool(out["embed_text"])
    out["use_scope"] = bool(out["use_scope"])
    for key in ("date_from", "date_to"):
        value = out.get(key)
        iso = getattr(value, "isoformat", None)
        if callable(iso):
            out[key] = iso()
    return json_safe(out)


def _seed_id(params: Any) -> int | None:
    if not isinstance(params, dict):
        return None
    raw = params.get("seed_external_id")
    if raw is None:
        raw = params.get("peer_external_id")
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


async def _attach_seed_peers(conn: Any, jobs: list[dict[str, Any]], *, data_dir: Any) -> list[dict[str, Any]]:
    seeds = [sid for job in jobs if (sid := _seed_id(job.get("params"))) is not None]
    peers: dict[int, dict[str, Any]] = {}
    if seeds:
        rows = await conn.execute(
            f"SELECT {PUBLIC_PEER_COLUMNS} FROM peers WHERE external_id = ANY(%s)",
            (seeds,),
        )
        for row in await rows.fetchall():
            peer = public_peer(dict(row), data_dir=data_dir)
            peers[int(peer["external_id"])] = peer
    for job in jobs:
        sid = _seed_id(job.get("params"))
        job["seed_peer"] = peers.get(sid) if sid is not None else None
    return jobs


_MEDIA_KINDS = ("image", "video", "gif", "audio", "document")


def _int_ids(values: Any) -> list[int]:
    ids: list[int] = []
    if not isinstance(values, list):
        return ids
    seen: set[int] = set()
    for value in values:
        try:
            item = int(value)
        except (TypeError, ValueError):
            continue
        if item not in seen:
            seen.add(item)
            ids.append(item)
    return ids


def _visited_peer_ids(job: dict[str, Any]) -> list[int]:
    progress = job.get("progress") if isinstance(job.get("progress"), dict) else {}
    ids = _int_ids(progress.get("visited_peer_ids"))
    seen = set(ids)
    for raw in (_seed_id(job.get("params")), progress.get("current_peer")):
        if raw is None:
            continue
        try:
            item = int(raw)
        except (TypeError, ValueError):
            continue
        if item not in seen:
            seen.add(item)
            ids.append(item)
    return ids


def _has_job_stats(progress: Any) -> bool:
    return isinstance(progress, dict) and isinstance(progress.get("stats"), dict) and "messages" in progress["stats"]


async def _message_stats_for_peers(conn: Any, peer_ids: list[int]) -> dict[str, int]:
    empty = {"messages": 0, **{kind: 0 for kind in _MEDIA_KINDS}}
    if not peer_ids:
        return empty
    row = await conn.execute(
        f"""
        SELECT
          COUNT(*) AS messages,
          COUNT(*) FILTER (WHERE {stored_kind_is("image")}) AS image,
          COUNT(*) FILTER (WHERE {stored_kind_is("video")}) AS video,
          COUNT(*) FILTER (WHERE {stored_kind_is("gif")}) AS gif,
          COUNT(*) FILTER (WHERE {stored_kind_is("audio")}) AS audio,
          COUNT(*) FILTER (WHERE {stored_kind_is("document")}) AS document
        FROM messages
        WHERE peer_external_id = ANY(%s)
        """,
        (peer_ids,),
    )
    data = await row.fetchone()
    if data is None:
        return empty
    return {
        "messages": int(data["messages"] or 0),
        **{kind: int(data[kind] or 0) for kind in _MEDIA_KINDS},
    }


def _finished_detail(peers_done: Any) -> str:
    try:
        count = int(peers_done)
    except (TypeError, ValueError):
        return "Finished"
    noun = "peer" if count == 1 else "peers"
    return f"Finished ({count} {noun})"


async def _attach_job_stats(conn: Any, jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for job in jobs:
        if job.get("task_type") != "forward_snowball":
            continue
        progress = dict(job.get("progress") or {})
        if job.get("status") == "succeeded":
            stats = progress.get("stats") if _has_job_stats(progress) else None
            if not isinstance(stats, dict):
                computed = await _message_stats_for_peers(conn, _visited_peer_ids(job))
                peers_done = progress.get("peers_done")
                try:
                    computed["peers"] = int(peers_done)
                except (TypeError, ValueError):
                    computed["peers"] = len(_visited_peer_ids(job))
                stats = computed
                progress["stats"] = stats
                progress["detail"] = _finished_detail(
                    progress.get("peers_done") if progress.get("peers_done") is not None else stats.get("peers")
                )
                await conn.execute(
                    """
                    UPDATE jobs
                    SET progress = COALESCE(progress, '{}'::jsonb) || %s
                    WHERE id = %s
                    """,
                    (Jsonb(json_safe(progress)), job["id"]),
                )
                await conn.commit()
            else:
                progress["stats"] = stats
                progress["detail"] = _finished_detail(
                    progress.get("peers_done") if progress.get("peers_done") is not None else stats.get("peers")
                )
            job["progress"] = progress
        elif isinstance(progress.get("detail"), str) and progress["detail"].startswith("Snowball finished"):
            progress["detail"] = progress["detail"].replace("Snowball finished", "Finished", 1)
            job["progress"] = progress
    return jobs


@router.get("/jobs")
async def list_jobs(limit: int = 50) -> dict[str, Any]:
    settings = load_settings()
    async with get_conn(settings) as conn:
        rows = await conn.execute(
            """
            SELECT id, task_type, status, params, progress, error,
                   created_at, started_at, finished_at
            FROM jobs
            ORDER BY
              CASE WHEN status IN ('running', 'queued') THEN 0 ELSE 1 END,
              COALESCE(started_at, created_at) DESC,
              created_at DESC
            LIMIT %s
            """,
            (min(max(limit, 1), 200),),
        )
        items = await rows.fetchall()
        jobs = await _attach_seed_peers(conn, [dict(row) for row in items], data_dir=settings.data_dir)
        jobs = await _attach_job_stats(conn, jobs)
    return {"jobs": jobs}


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
        jobs = await _attach_seed_peers(conn, [dict(job)], data_dir=settings.data_dir)
        jobs = await _attach_job_stats(conn, jobs)
    return jobs[0]


@router.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: UUID) -> dict[str, Any]:
    settings = load_settings()
    async with get_conn(settings) as conn:
        row = await conn.execute(
            """
            UPDATE jobs
            SET status = 'cancelled',
                finished_at = now(),
                heartbeat_at = now()
            WHERE id = %s AND status IN ('queued', 'running')
            RETURNING id, task_type, status, params, progress, error,
                      created_at, started_at, finished_at
            """,
            (job_id,),
        )
        job = await row.fetchone()
        if job is None:
            existing = await conn.execute(
                """
                SELECT id, task_type, status, params, progress, error,
                       created_at, started_at, finished_at
                FROM jobs WHERE id = %s
                """,
                (job_id,),
            )
            found = await existing.fetchone()
            if found is None:
                raise HTTPException(status_code=404, detail="Job not found")
            if found["status"] != "cancelled":
                raise HTTPException(
                    status_code=409, detail=f"Job is {found['status']} and cannot be stopped."
                )
            job = found
        else:
            # Publish Stopped before clearing peer flags. Those rows can be locked
            # for the whole time a scrape is waiting on Telegram.
            await conn.commit()
        if lane_for(job["task_type"]) == "scrape":
            try:
                await conn.execute("SET LOCAL lock_timeout = '2s'")
                await conn.execute(
                    "UPDATE peers SET is_scraping = false, scrape_detail = NULL WHERE is_scraping = true"
                )
                await conn.commit()
            except psycopg.errors.LockNotAvailable:
                await conn.rollback()
                lg.info("job %s cancelled; peer flags stay until the scrape releases them", job_id)
        jobs = await _attach_seed_peers(conn, [dict(job)], data_dir=settings.data_dir)
        jobs = await _attach_job_stats(conn, jobs)
    return jobs[0]


@router.post("/jobs")
async def create_job(body: CreateJobIn) -> dict[str, Any]:
    settings = load_settings()
    params = dict(body.params)
    async with get_conn(settings) as conn:
        session = await conn.execute("SELECT id FROM telegram_sessions LIMIT 1")
        if await session.fetchone() is None:
            raise HTTPException(status_code=400, detail="Connect a Telegram account first.")
        lane = lane_for(body.task_type)
        if await live_job_in_lane(conn, lane):
            raise HTTPException(status_code=409, detail=live_conflict_detail(lane))

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
            if params.get("use_scope") and not params.get("embed_images"):
                raise HTTPException(
                    status_code=400,
                    detail="Steer by scope needs image embedding on.",
                )

        if body.task_type == "embed":
            targets = params.get("targets") or ["text", "images"]
            if isinstance(targets, str):
                targets = [targets]
            params["targets"] = [str(item) for item in targets]
            gate = {
                "embed_text": "text" in params["targets"],
                "embed_images": "images" in params["targets"] or "image" in params["targets"],
            }
            try:
                assert_snowball_embed_gate(settings, gate)
            except EmbeddingGateError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

        inserted = await conn.execute(
            """
            INSERT INTO jobs (task_type, status, params)
            VALUES (%s, 'queued', %s)
            RETURNING id, task_type, status, params, progress, created_at
            """,
            (body.task_type, Jsonb(json_safe(params))),
        )
        job = await inserted.fetchone()
        await conn.commit()
        assert job is not None
        jobs = await _attach_seed_peers(conn, [dict(job)], data_dir=settings.data_dir)
    return jobs[0]


class SeedResolveIn(BaseModel):
    query: str = Field(..., min_length=1)


async def _local_seed_peer(conn: Any, query: str, kind: str) -> dict[str, Any] | None:
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
        return dict(hit)
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
        return dict(hit)
    row = await conn.execute(
        """
        SELECT external_id, username
        FROM peers
        WHERE usernames IS NOT NULL
          AND EXISTS (
            SELECT 1
            FROM jsonb_array_elements(usernames) AS handle
            WHERE lower(handle->>'username') = lower(%s)
          )
        LIMIT 1
        """,
        (query,),
    )
    hit = await row.fetchone()
    return dict(hit) if hit is not None else None


@router.post("/snowball/resolve")
async def resolve_seed(body: SeedResolveIn) -> dict[str, Any]:
    """Resolve a seed from the local catalog, or from Telegram if it is not stored yet."""
    settings = load_settings()
    query = body.query.strip().lstrip("@")
    kind = infer_peer_id_kind(query)
    stored: dict[str, Any] | None = None
    async with get_conn(settings) as conn:
        stored = await _local_seed_peer(conn, query, kind)
        if stored is not None:
            peer = await load_public_peer(
                conn, int(stored["external_id"]), data_dir=settings.data_dir
            )
            if peer is not None:
                return {"peer": peer, "resolved": False}

    from telethon.errors import (
        ChannelPrivateError,
        ChatForbiddenError,
        FloodWaitError,
        UsernameInvalidError,
        UsernameNotOccupiedError,
    )
    from telegram_snowball.telegram.client import telegram_client
    from telegram_snowball.telegram.materialize import materialize_peer

    lookup: str | int = query
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
