from __future__ import annotations

import asyncio
import logging
from uuid import UUID

from telegram_snowball.config import Settings
from telegram_snowball.db import apply_schema, connect_with_retry
from telegram_snowball.jobs import runners_for
from telegram_snowball.jobs.lanes import tasks_for_kind
from telegram_snowball.jobs.progress import JobCancelled

lg = logging.getLogger(__name__)


async def _claim_job(conn, *, tasks: tuple[str, ...]) -> dict | None:
    task_list = list(tasks)
    row = await conn.execute(
        """
        WITH next_job AS (
            SELECT id
            FROM jobs
            WHERE status = 'queued'
              AND task_type = ANY(%s)
            ORDER BY created_at ASC
            FOR UPDATE SKIP LOCKED
            LIMIT 1
        )
        UPDATE jobs
        SET status = 'running', started_at = now(), heartbeat_at = now()
        FROM next_job
        WHERE jobs.id = next_job.id
          AND NOT EXISTS (
              SELECT 1
              FROM jobs running
              WHERE running.status = 'running'
                AND running.id <> jobs.id
                AND running.task_type = ANY(%s)
          )
        RETURNING jobs.id, jobs.task_type, jobs.params
        """,
        (task_list, task_list),
    )
    data = await row.fetchone()
    await conn.commit()
    return data


async def _finish(
    conn,
    job_id: UUID,
    *,
    ok: bool,
    error: str | None = None,
    clear_scraping: bool,
) -> None:
    await conn.execute(
        """
        UPDATE jobs
        SET status = %s,
            error = %s,
            finished_at = now(),
            heartbeat_at = now()
        WHERE id = %s AND status <> 'cancelled'
        """,
        ("succeeded" if ok else "failed", error, job_id),
    )
    if clear_scraping:
        await conn.execute(
            "UPDATE peers SET is_scraping = false, scrape_detail = NULL WHERE is_scraping = true"
        )
    await conn.commit()


async def run_worker(
    settings: Settings,
    *,
    kind: str | None = None,
    worker_id: str | None = None,
) -> None:
    kind = (kind or settings.snowball_worker_kind or "scrape").strip().lower()
    if kind not in {"scrape", "embed"}:
        kind = "scrape"
    tasks = tasks_for_kind(kind)
    runners = runners_for(kind)
    worker_id = worker_id or f"{kind}-1"
    clear_scraping = kind == "scrape"
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    conn = await connect_with_retry(settings.postgres_dsn)
    await apply_schema(conn)
    await conn.execute(
        """
        UPDATE jobs
        SET status = 'failed',
            error = COALESCE(error, 'Worker restarted before the job finished'),
            finished_at = COALESCE(finished_at, now()),
            heartbeat_at = now()
        WHERE status = 'running'
          AND task_type = ANY(%s)
        """,
        (list(tasks),),
    )
    if clear_scraping:
        await conn.execute(
            "UPDATE peers SET is_scraping = false, scrape_detail = NULL WHERE is_scraping = true"
        )
    await conn.commit()
    lg.info("worker %s ready kind=%s tasks=%s", worker_id, kind, ",".join(tasks))
    try:
        while True:
            job = await _claim_job(conn, tasks=tasks)
            if job is None:
                await asyncio.sleep(1.0)
                continue
            job_id = job["id"]
            task_type = job["task_type"]
            params = job["params"] or {}
            runner = runners.get(task_type)
            lg.info("claimed %s %s", task_type, job_id)
            if runner is None:
                await _finish(
                    conn,
                    job_id,
                    ok=False,
                    error=f"Unknown task_type={task_type}",
                    clear_scraping=clear_scraping,
                )
                continue
            try:
                if kind == "embed" and task_type != "scope_rerank":
                    from telegram_snowball.embed.worklock import inference_lock

                    async with inference_lock():
                        await runner(conn, settings=settings, job_id=job_id, params=params)
                else:
                    await runner(conn, settings=settings, job_id=job_id, params=params)
                await _finish(conn, job_id, ok=True, clear_scraping=clear_scraping)
            except JobCancelled:
                lg.info("job %s cancelled", job_id)
                if clear_scraping:
                    await conn.execute(
                        "UPDATE peers SET is_scraping = false, scrape_detail = NULL WHERE is_scraping = true"
                    )
                    await conn.commit()
            except Exception as exc:
                lg.exception("job %s failed", job_id)
                await _finish(
                    conn, job_id, ok=False, error=str(exc), clear_scraping=clear_scraping
                )
    finally:
        await conn.close()
