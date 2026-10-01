"""Watch a job for cancellation without importing the job runners."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from typing import Any, TypeVar
from uuid import UUID

from psycopg import AsyncConnection
from psycopg.pq import TransactionStatus

_T = TypeVar("_T")


class JobCancelled(Exception):
    """The job was cancelled while the worker was still running it."""


async def end_transaction(conn: AsyncConnection[Any], *, rollback: bool = False) -> None:
    """Finish the open transaction so row locks are not held across network calls."""
    status = conn.info.transaction_status
    if status == TransactionStatus.IDLE:
        return
    if rollback or status == TransactionStatus.INERROR:
        await conn.rollback()
        return
    await conn.commit()


async def job_is_cancelled(conn: AsyncConnection[Any], job_id: UUID) -> bool:
    row = await conn.execute("SELECT status FROM jobs WHERE id = %s", (job_id,))
    data = await row.fetchone()
    return data is not None and data["status"] == "cancelled"


async def await_unless_cancelled(
    conn: AsyncConnection[Any],
    job_id: UUID,
    awaitable: Awaitable[_T],
    *,
    poll_s: float = 0.5,
) -> _T:
    """Run network work without holding database locks, and stop it once the job is cancelled."""
    await end_transaction(conn)
    task = asyncio.ensure_future(awaitable)
    try:
        while True:
            done, _pending = await asyncio.wait({task}, timeout=poll_s)
            if task in done:
                return task.result()
            if await job_is_cancelled(conn, job_id):
                await end_transaction(conn, rollback=True)
                await _stop_task(task)
                raise JobCancelled()
            await end_transaction(conn, rollback=True)
    except BaseException:
        if not task.done():
            await _stop_task(task)
        raise


async def _stop_task(task: asyncio.Future[Any]) -> None:
    task.cancel()
    try:
        await asyncio.wait_for(task, timeout=2)
    except (asyncio.CancelledError, asyncio.TimeoutError, Exception):
        return
