from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from psycopg.types.json import Jsonb
from psycopg import AsyncConnection


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
        (Jsonb(progress), job_id),
    )
    await conn.commit()


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
