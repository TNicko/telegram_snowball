from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from telegram_snowball.telegram.first_message import (
    first_message_missing,
    record_first_visible_message,
)


class _Result:
    def __init__(self, row: dict | None) -> None:
        self._row = row

    async def fetchone(self) -> dict | None:
        return self._row


class _Conn:
    def __init__(self, row: dict | None) -> None:
        self.row = row
        self.updates: list[tuple[str, tuple]] = []

    async def execute(self, sql: str, params: tuple | None = None) -> _Result:
        if params is not None and "UPDATE peers" in sql:
            self.updates.append((sql, params))
        return _Result(self.row)


async def test_first_message_missing_when_date_absent() -> None:
    conn = _Conn({"first_message_id": 1, "first_message_at": None})
    assert await first_message_missing(conn, 99) is True


async def test_first_message_present() -> None:
    conn = _Conn(
        {
            "first_message_id": 1,
            "first_message_at": datetime(2024, 6, 1, tzinfo=timezone.utc),
        }
    )
    assert await first_message_missing(conn, 99) is False


async def test_record_first_visible_message_skips_invalid() -> None:
    conn = _Conn(None)
    await record_first_visible_message(conn, 1, SimpleNamespace(id=None, date=None))
    assert conn.updates == []


async def test_record_first_visible_message_writes() -> None:
    conn = _Conn(None)
    date = datetime(2024, 6, 1, tzinfo=timezone.utc)
    await record_first_visible_message(conn, 42, SimpleNamespace(id=7, date=date))
    assert len(conn.updates) == 1
    assert conn.updates[0][1] == (7, date, 42, 7)
