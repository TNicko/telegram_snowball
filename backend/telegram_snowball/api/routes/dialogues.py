from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from psycopg.types.json import Jsonb

from telegram_snowball.catalog import attach_catalog_stats, load_catalog_stats
from telegram_snowball.config import load_settings
from telegram_snowball.db import get_conn
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
    return out


PUBLIC_PEER_COLUMNS = """
    external_id, peer_type, title, username, about, participants_count,
    photo_path, photo_media_kind, is_scraping, scrape_detail, messages_scraped,
    last_message_id, last_message_at, created_at, updated_at
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
async def sync_dialogues() -> dict[str, Any]:
    """Queue peer-only dialogue materialize if one is not already active or done."""
    settings = load_settings()
    async with get_conn(settings) as conn:
        session = await conn.execute("SELECT id FROM telegram_sessions LIMIT 1")
        if await session.fetchone() is None:
            raise HTTPException(status_code=400, detail="Connect a Telegram account first.")

        active = await conn.execute(
            """
            SELECT id, task_type, status, params, progress, error, created_at, started_at, finished_at
            FROM jobs
            WHERE status IN ('queued', 'running')
            ORDER BY created_at DESC
            LIMIT 1
            """
        )
        current = await active.fetchone()
        if current is not None:
            if current["task_type"] == "fetch_dialogues":
                return {"started": False, "job": dict(current)}
            return {"started": False, "blocked": True, "job": dict(current)}

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

        params = {"mode": "materialize", "messages": False, "participants": False}
        inserted = await conn.execute(
            """
            INSERT INTO jobs (task_type, status, params)
            VALUES ('fetch_dialogues', 'queued', %s)
            RETURNING id, task_type, status, params, progress, created_at, started_at, finished_at
            """,
            (Jsonb(params),),
        )
        job = await inserted.fetchone()
        await conn.commit()
    assert job is not None
    return {"started": True, "job": dict(job)}
