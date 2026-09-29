"""Scrape vs embed job lanes so Telegram work and model/encode can overlap."""

from __future__ import annotations

from typing import Any

SCRAPE_TASKS: tuple[str, ...] = ("fetch_dialogues", "forward_snowball")
EMBED_TASKS: tuple[str, ...] = ("download_model", "embed", "scope_rerank")


def lane_for(task_type: str) -> str:
    if task_type in EMBED_TASKS:
        return "embed"
    if task_type in SCRAPE_TASKS:
        return "scrape"
    raise ValueError(f"Unknown task_type={task_type}")


def tasks_for_kind(kind: str) -> tuple[str, ...]:
    if kind == "embed":
        return EMBED_TASKS
    return SCRAPE_TASKS


def live_conflict_detail(lane: str) -> str:
    if lane == "embed":
        return "A model download, embed, or Scope rescore job is already queued or running."
    return "A Telegram scrape job is already queued or running. v1 uses one session at a time."


async def live_job_in_lane(conn: Any, lane: str) -> dict[str, Any] | None:
    row = await conn.execute(
        """
        SELECT id, task_type, status, params, progress, error,
               created_at, started_at, finished_at
        FROM jobs
        WHERE status IN ('queued', 'running')
          AND task_type = ANY(%s)
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (list(tasks_for_kind(lane)),),
    )
    data = await row.fetchone()
    return dict(data) if data is not None else None
