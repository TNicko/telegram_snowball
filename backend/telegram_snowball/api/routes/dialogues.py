from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from psycopg.types.json import Jsonb

from telegram_snowball.catalog import attach_catalog_stats, load_catalog_stats, load_peer_coverage
from telegram_snowball.config import load_settings
from telegram_snowball.db import get_conn
from telegram_snowball.jobs.lanes import live_job_in_lane
from telegram_snowball.jsonutil import json_safe
from telegram_snowball.telegram.profile_photos import sniff_profile_media

router = APIRouter()


def public_peer(row: dict[str, Any], *, data_dir: Any | None = None) -> dict[str, Any]:
    out = dict(row)
    photo_path = out.get("photo_path")
    kind = out.get("photo_media_kind")
    if photo_path and data_dir is not None:
        dest = data_dir / str(photo_path)
        sniffed, _content_type = sniff_profile_media(dest) if dest.is_file() else (None, None)
        kind = sniffed or kind
    out["photo_media_kind"] = kind if kind in ("image", "video") else None
    out["photo_url"] = f"/api/peers/{out['external_id']}/photo" if out["photo_media_kind"] else None
    for key in ("scope_score", "forward_score"):
        raw = out.get(key)
        try:
            out[key] = round(float(raw), 4) if raw is not None else 0.0
        except (TypeError, ValueError):
            out[key] = 0.0
    return out


PUBLIC_PEER_COLUMNS = """
    external_id, peer_type, title, username, about, participants_count,
    photo_path, photo_media_kind, is_scraping, scrape_detail, messages_scraped,
    last_message_id, last_message_at, created_at, updated_at,
    scope_score, forward_score
"""


async def load_public_peer(conn: Any, external_id: int, *, data_dir: Any) -> dict[str, Any] | None:
    row = await conn.execute(
        f"SELECT {PUBLIC_PEER_COLUMNS} FROM peers WHERE external_id = %s",
        (external_id,),
    )
    data = await row.fetchone()
    if data is None:
        return None
    return public_peer(dict(data), data_dir=data_dir)


@router.get("/peers")
async def list_peers() -> dict[str, Any]:
    settings = load_settings()
    async with get_conn(settings) as conn:
        rows = await conn.execute(
            f"""
            SELECT {PUBLIC_PEER_COLUMNS}
            FROM peers
            ORDER BY created_at DESC, external_id DESC
            """
        )
        items = await rows.fetchall()
        fetch_ids, media_cov, message_stats = await load_catalog_stats(conn)
    peers = []
    for row in items:
        peer = public_peer(dict(row), data_dir=settings.data_dir)
        peers.append(attach_catalog_stats(peer, fetch_ids=fetch_ids, media_cov=media_cov, message_stats=message_stats))
    return {"peers": peers}


@router.get("/peers/{external_id}/coverage")
async def peer_coverage(external_id: int) -> dict[str, Any]:
    settings = load_settings()
    async with get_conn(settings) as conn:
        peer = await load_public_peer(conn, external_id, data_dir=settings.data_dir)
        if peer is None:
            raise HTTPException(status_code=404, detail="Peer not found")
        coverage = await load_peer_coverage(conn, peer)
        if coverage["timeline"]["start"] is None:
            from telegram_snowball.telegram.first_message import backfill_first_visible_message

            if await backfill_first_visible_message(conn, settings, external_id):
                await conn.commit()
                coverage = await load_peer_coverage(conn, peer)
        return coverage


@router.get("/peers/{external_id}/photo")
async def peer_photo(external_id: int) -> FileResponse:
    settings = load_settings()
    async with get_conn(settings) as conn:
        row = await conn.execute(
            "SELECT photo_path FROM peers WHERE external_id = %s",
            (external_id,),
        )
        data = await row.fetchone()
    if not data or not data["photo_path"]:
        raise HTTPException(status_code=404, detail="No profile photo")
    dest = (settings.data_dir / str(data["photo_path"])).resolve()
    root = settings.data_dir.resolve()
    if root not in dest.parents and dest != root:
        raise HTTPException(status_code=404, detail="Invalid photo path")
    if not dest.is_file():
        raise HTTPException(status_code=404, detail="Photo file missing")
    kind, content_type = sniff_profile_media(dest)
    if kind not in ("image", "video") or not content_type:
        raise HTTPException(status_code=404, detail="Photo file missing")
    return FileResponse(dest, media_type=content_type)


@router.post("/dialogues/sync")
async def sync_dialogues(force: bool = False) -> dict[str, Any]:
    """Queue peer-only dialogue materialize if one is not already active or done.

    Skips when a successful sync exists, or when peers are already stored
    (fresh restore keeps dialogues and truncates jobs). Pass force=true to
    queue another pass for new chats.
    """
    settings = load_settings()
    async with get_conn(settings) as conn:
        session = await conn.execute("SELECT id FROM telegram_sessions LIMIT 1")
        if await session.fetchone() is None:
            raise HTTPException(status_code=400, detail="Connect a Telegram account first.")

        current = await live_job_in_lane(conn, "scrape")
        if current is not None:
            if current["task_type"] == "fetch_dialogues":
                return {"started": False, "job": current}
            return {"started": False, "blocked": True, "job": current}

        if not force:
            done = await conn.execute(
                """
                SELECT id, task_type, status, params, progress, error, created_at, started_at, finished_at
                FROM jobs
                WHERE task_type = 'fetch_dialogues'
                  AND status = 'succeeded'
                ORDER BY finished_at DESC NULLS LAST
                LIMIT 1
                """
            )
            finished = await done.fetchone()
            if finished is not None:
                return {"started": False, "job": dict(finished)}

            # Restore / fresh dump keeps dialogue peers but truncates jobs.
            # Do not hit Telegram again just because the success row is gone.
            stored = await conn.execute("SELECT EXISTS (SELECT 1 FROM peers LIMIT 1) AS has_peers")
            has_peers = await stored.fetchone()
            if has_peers is not None and has_peers["has_peers"]:
                return {"started": False, "job": None}

        params = {"mode": "materialize", "messages": False, "participants": False}
        inserted = await conn.execute(
            """
            INSERT INTO jobs (task_type, status, params)
            VALUES ('fetch_dialogues', 'queued', %s)
            RETURNING id, task_type, status, params, progress, created_at, started_at, finished_at
            """,
            (Jsonb(json_safe(params)),),
        )
        job = await inserted.fetchone()
        await conn.commit()
    assert job is not None
    return {"started": True, "job": dict(job)}
