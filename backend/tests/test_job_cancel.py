from __future__ import annotations

import asyncio
from uuid import uuid4

from psycopg.pq import TransactionStatus

from telegram_snowball.jobwait import JobCancelled, await_unless_cancelled


class _Row:
    def __init__(self, status: str) -> None:
        self._status = status

    async def fetchone(self) -> dict[str, str]:
        return {"status": self._status}


class _Conn:
    def __init__(self) -> None:
        self.status = "running"
        self.tx = TransactionStatus.INTRANS
        self.commits = 0
        self.rollbacks = 0

    @property
    def info(self) -> _Conn:
        return self

    @property
    def transaction_status(self) -> TransactionStatus:
        return self.tx

    async def commit(self) -> None:
        self.commits += 1
        self.tx = TransactionStatus.IDLE

    async def rollback(self) -> None:
        self.rollbacks += 1
        self.tx = TransactionStatus.IDLE

    async def execute(self, _sql: str, _params: object = None) -> _Row:
        self.tx = TransactionStatus.INTRANS
        return _Row(self.status)


def test_network_work_stops_when_the_job_is_cancelled() -> None:
    conn = _Conn()

    async def scenario() -> None:
        started = asyncio.Event()

        async def slow() -> str:
            assert conn.transaction_status == TransactionStatus.IDLE
            started.set()
            await asyncio.sleep(30)
            return "finished"

        task = asyncio.create_task(await_unless_cancelled(conn, uuid4(), slow(), poll_s=0.05))
        await started.wait()
        conn.status = "cancelled"
        try:
            await asyncio.wait_for(task, timeout=2)
        except JobCancelled:
            pass
        else:
            raise AssertionError("download kept running after the job was cancelled")
        assert conn.transaction_status == TransactionStatus.IDLE

    asyncio.run(scenario())
    assert conn.commits >= 1
