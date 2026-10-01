from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from psycopg import AsyncConnection
from psycopg.types.json import Jsonb

from telegram_snowball.jobwait import (
    JobCancelled,
    await_unless_cancelled,
    end_transaction,
    job_is_cancelled,
)
from telegram_snowball.jsonutil import json_safe

__all__ = [
    "JobCancelled",
    "await_unless_cancelled",
    "end_transaction",
    "job_is_cancelled",
    "mark_peer_idle",
    "mark_peer_scraping",
    "raise_if_cancelled",
    "update_job_progress",
    "utcnow",
]


async def update_job_progress(
    conn: AsyncConnection[Any],
    job_id: UUID,
    progress: dict[str, Any],
) -> None:
    await conn.execute(
        """
        UPDATE jobs
        SET progress = COALESCE(progress, '{}'::jsonb) || %s,
            heartbeat_at = now()
        WHERE id = %s
        """,
        (Jsonb(json_safe(progress)), job_id),
    )
    await conn.commit()


async def raise_if_cancelled(conn: AsyncConnection[Any], job_id: UUID) -> None:
    if await job_is_cancelled(conn, job_id):
        raise JobCancelled()


async def mark_peer_scraping(
    conn: AsyncConnection[Any],
    external_id: int,
    *,
    detail: str,
    messages_scraped: int | None = None,
) -> None:
    if messages_scraped is None:
        await conn.execute(
            """
            UPDATE peers
            SET is_scraping = true, scrape_detail = %s, updated_at = now()
            WHERE external_id = %s
            """,
            (detail, external_id),
        )
    else:
        await conn.execute(
            """
            UPDATE peers
            SET is_scraping = true, scrape_detail = %s,
                messages_scraped = %s, updated_at = now()
            WHERE external_id = %s
            """,
            (detail, messages_scraped, external_id),
        )


async def mark_peer_idle(conn: AsyncConnection[Any], external_id: int) -> None:
    await conn.execute(
        """
        UPDATE peers
        SET is_scraping = false, scrape_detail = NULL, updated_at = now()
        WHERE external_id = %s
        """,
        (external_id,),
    )


def utcnow() -> datetime:
    return datetime.now(UTC)
