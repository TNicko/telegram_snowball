from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from telegram_snowball.config import load_settings
from telegram_snowball.db import get_conn
from telegram_snowball.models_health import models_health
from telegram_snowball.telegram.profile_photos import sniff_profile_media

router = APIRouter()

_ACCOUNT_SELECT = """
    SELECT a.id, a.telegram_user_id, a.phone, a.username, a.first_name, a.last_name,
           COALESCE(a.photo_path, p.photo_path) AS photo_path,
           COALESCE(a.photo_media_kind, p.photo_media_kind) AS photo_media_kind
    FROM telegram_accounts a
    JOIN telegram_sessions s ON s.account_id = a.id
    LEFT JOIN peers p ON p.external_id = a.telegram_user_id
    LIMIT 1
"""


def public_account(row: dict[str, Any], *, data_dir: Any) -> dict[str, Any]:
    out = dict(row)
    photo_path = out.get("photo_path")
    kind = out.get("photo_media_kind")
    if photo_path:
        dest = data_dir / str(photo_path)
        sniffed, _content_type = sniff_profile_media(dest) if dest.is_file() else (None, None)
        kind = sniffed or kind
    out["photo_media_kind"] = kind if kind in ("image", "video") else None
    out["photo_url"] = "/api/account/photo" if out["photo_media_kind"] else None
    return out


@router.get("/health")
async def health() -> dict[str, bool]:
    settings = load_settings()
    try:
        async with get_conn(settings) as conn:
            await conn.execute("SELECT 1")
    except Exception as exc:
        raise HTTPException(status_code=503, detail="database unavailable") from exc
    return {"ok": True}


@router.get("/status")
async def get_status() -> dict:
    settings = load_settings()
    async with get_conn(settings) as conn:
        creds = await conn.execute(
            "SELECT 1 FROM app_settings WHERE key = 'telegram_credentials'"
        )
        has_credentials = await creds.fetchone() is not None
        account_row = await conn.execute(_ACCOUNT_SELECT)
        account = await account_row.fetchone()
        job_row = await conn.execute(
            """
            SELECT id, task_type, status, params, progress, error, created_at, started_at, finished_at
            FROM jobs
            WHERE status IN ('queued', 'running')
            ORDER BY created_at DESC
            LIMIT 1
            """
        )
        active_job = await job_row.fetchone()
    return {
        "has_credentials": has_credentials,
        "has_session": account is not None,
        "setup_complete": account is not None,
        "account": public_account(dict(account), data_dir=settings.data_dir) if account else None,
        "models": models_health(settings),
        "active_job": dict(active_job) if active_job else None,
        "limits": {"max_sessions": 1, "max_workers": 1},
    }


@router.get("/account/photo")
async def account_photo() -> FileResponse:
    settings = load_settings()
    async with get_conn(settings) as conn:
        row = await conn.execute(_ACCOUNT_SELECT)
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
