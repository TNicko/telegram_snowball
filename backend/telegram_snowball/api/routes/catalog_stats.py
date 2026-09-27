from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from telegram_snowball.catalog_storage import catalog_storage_stats
from telegram_snowball.config import load_settings
from telegram_snowball.db import get_conn

router = APIRouter()


@router.get("/catalog/stats")
async def get_catalog_stats() -> dict[str, Any]:
    settings = load_settings()
    async with get_conn(settings) as conn:
        return await catalog_storage_stats(conn, settings)
