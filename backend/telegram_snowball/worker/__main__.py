from __future__ import annotations

import asyncio
import logging
from uuid import UUID

from telegram_snowball.config import Settings, load_settings
from telegram_snowball.db import apply_schema, connect_with_retry
from telegram_snowball.jobs import TASK_RUNNERS

lg = logging.getLogger(__name__)

WORKER_ID = "local-1"


async def _claim_job(conn) -> dict | None:
    row = await conn.execute(
        """
        WITH next_job AS (
            SELECT id
            FROM jobs
            WHERE status = 'queued'
            ORDER BY created_at ASC
            FOR UPDATE SKIP LOCKED
            LIMIT 1
        )
        UPDATE jobs
        SET status = 'running', started_at = now(), heartbeat_at = now()
        FROM next_job
        WHERE jobs.id = next_job.id
          AND NOT EXISTS (SELECT 1 FROM jobs running WHERE running.status = 'running' AND running.id <> jobs.id)
        RETURNING jobs.id, jobs.task_type, jobs.params
        """
    )
    data = await row.fetchone()
    await conn.commit()
    return data


async def _finish(conn, job_id: UUID, *, ok: bool, error: str | None = None) -> None:
    await conn.execute(
        """
        UPDATE jobs
        SET status = %s,
            error = %s,
            finished_at = now(),
            heartbeat_at = now()
        WHERE id = %s
        """,
        ("succeeded" if ok else "failed", error, job_id),
    )
    await conn.execute(
        "UPDATE peers SET is_scraping = false, scrape_detail = NULL WHERE is_scraping = true"
    )
    await conn.commit()


async def run_worker(settings: Settings) -> None:
    logging.basicConfig(level=settings.log_level.upper(), format="%(asctime)s %(levelname)s %(name)s %(message)s")
    conn = await connect_with_retry(settings.postgres_dsn)
    await apply_schema(conn)
    lg.info("worker %s ready (max 1 job, max 1 session)", WORKER_ID)
    try:
        while True:
            job = await _claim_job(conn)
            if job is None:
                await asyncio.sleep(1.0)
                continue
            job_id = job["id"]
            task_type = job["task_type"]
            params = job["params"] or {}
            runner = TASK_RUNNERS.get(task_type)
            lg.info("claimed %s %s", task_type, job_id)
            if runner is None:
                await _finish(conn, job_id, ok=False, error=f"Unknown task_type={task_type}")
                continue
            try:
                await runner(conn, settings=settings, job_id=job_id, params=params)
                await _finish(conn, job_id, ok=True)
            except Exception as exc:
                lg.exception("job %s failed", job_id)
                await _finish(conn, job_id, ok=False, error=str(exc))
    finally:
        await conn.close()


def main() -> None:
    settings = load_settings()
    asyncio.run(run_worker(settings))


if __name__ == "__main__":
    main()
