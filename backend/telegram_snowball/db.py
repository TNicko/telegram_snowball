from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from importlib.resources import files
from typing import Any

import psycopg
from psycopg.rows import dict_row

from telegram_snowball.config import Settings

lg = logging.getLogger(__name__)


async def connect(dsn: str) -> psycopg.AsyncConnection[Any]:
    return await psycopg.AsyncConnection.connect(dsn, row_factory=dict_row, autocommit=False)


async def connect_with_retry(dsn: str, *, attempts: int = 30) -> psycopg.AsyncConnection[Any]:
    last: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return await connect(dsn)
        except Exception as exc:
            last = exc
            lg.warning("postgres not ready (attempt %s/%s): %s", attempt, attempts, exc)
            await asyncio.sleep(1)
    assert last is not None
    raise last


async def apply_schema(conn: psycopg.AsyncConnection[Any]) -> None:
    sql = files("telegram_snowball").joinpath("schema.sql").read_text(encoding="utf-8")
    await conn.execute(sql)
    await conn.commit()
    from telegram_snowball.telegram.forwards import backfill_forward_tables

    await backfill_forward_tables(conn)
    await conn.commit()
    from telegram_snowball.catalog import backfill_stored_media_kinds

    await backfill_stored_media_kinds(conn)
    await conn.commit()


@asynccontextmanager
async def get_conn(settings: Settings) -> AsyncIterator[psycopg.AsyncConnection[Any]]:
    conn = await connect(settings.postgres_dsn)
    try:
        yield conn
    finally:
        await conn.close()
