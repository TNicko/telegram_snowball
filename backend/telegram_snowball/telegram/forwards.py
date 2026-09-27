"""Unique forward edges plus per-message fan-out, matching messenger's graph tables.

``forward_edges`` is one row per unique directed pair (from → to) with a running
``forward_count``. ``forward_edge_messages`` records each forwarded message so
counts stay idempotent on re-scrape and the graph can be rebuilt without
scanning ``messages.fwd_from`` JSON.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from telegram_snowball.telegram.ids import (
    infer_peer_type_from_signed,
    is_snowball_target,
    signed_peer_id_from_raw_channel_id,
)


def _as_uuid(value: UUID | str | None) -> UUID | None:
    if isinstance(value, UUID):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return UUID(value.strip())
        except ValueError:
            return None
    return None


def _tl_name(value: Any) -> str:
    if isinstance(value, dict):
        raw = value.get("_") or value.get("tl") or ""
        return str(raw)
    return type(value).__name__


def _int_field(value: Any, key: str) -> int | None:
    if isinstance(value, dict):
        raw = value.get(key)
    else:
        raw = getattr(value, key, None)
    if raw is None or raw == "":
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def signed_peer_from_fwd_peer(peer: Any) -> int | None:
    if peer is None:
        return None
    name = _tl_name(peer)
    if "PeerChannel" in name:
        channel_id = _int_field(peer, "channel_id")
        if channel_id is not None:
            return signed_peer_id_from_raw_channel_id(channel_id)
    if "PeerChat" in name:
        chat_id = _int_field(peer, "chat_id")
        if chat_id is not None:
            return -abs(chat_id)
    if "PeerUser" in name:
        user_id = _int_field(peer, "user_id")
        if user_id is not None:
            return user_id
    return None


def signed_peer_from_fwd(fwd: Any) -> int | None:
    if fwd is None:
        return None
    for key in ("from_id", "saved_from_peer"):
        peer = fwd.get(key) if isinstance(fwd, dict) else getattr(fwd, key, None)
        signed = signed_peer_from_fwd_peer(peer)
        if signed is not None:
            return signed
    return None


def origin_telegram_id_from_fwd(fwd: Any) -> int | None:
    """Telegram message id of the original post, if the header carries one."""
    if fwd is None:
        return None
    for key in ("channel_post", "saved_from_msg_id"):
        raw = fwd.get(key) if isinstance(fwd, dict) else getattr(fwd, key, None)
        if raw is None or raw == "":
            continue
        try:
            value = int(raw)
        except (TypeError, ValueError):
            continue
        if value > 0:
            return value
    return None


def fwd_from_name(fwd: Any) -> str | None:
    if fwd is None:
        return None
    name = fwd.get("from_name") if isinstance(fwd, dict) else getattr(fwd, "from_name", None)
    if isinstance(name, str) and name.strip():
        return name.strip()
    return None


async def persist_forward_occurrence(
    conn: Any,
    *,
    from_peer_id: int,
    to_peer_id: int,
    message_id: UUID | str | None,
    message_date: datetime | None,
    telegram_message_id: int | None = None,
    from_name: str | None = None,
    from_peer_type: str | None = None,
    to_peer_type: str | None = None,
    bump_count: bool = True,
) -> bool:
    """Record one forwarded message. Returns True if the fan-out row is new."""
    message_uuid = _as_uuid(message_id)
    if (
        message_uuid is None
        or message_date is None
        or from_peer_id == to_peer_id
        or not is_snowball_target(from_peer_id)
        or not is_snowball_target(to_peer_id)
    ):
        return False
    from_type = from_peer_type or infer_peer_type_from_signed(from_peer_id)
    to_type = to_peer_type or infer_peer_type_from_signed(to_peer_id)
    await conn.execute(
        """
        INSERT INTO forward_edges (
            from_external_id, to_external_id, from_peer_type, to_peer_type,
            last_from_name, first_seen_at, last_seen_at, forward_count
        )
        VALUES (%s, %s, %s, %s, %s, now(), now(), 0)
        ON CONFLICT (from_external_id, to_external_id) DO UPDATE SET
            last_from_name = COALESCE(EXCLUDED.last_from_name, forward_edges.last_from_name),
            last_seen_at = now(),
            from_peer_type = COALESCE(EXCLUDED.from_peer_type, forward_edges.from_peer_type),
            to_peer_type = COALESCE(EXCLUDED.to_peer_type, forward_edges.to_peer_type)
        """,
        (from_peer_id, to_peer_id, from_type, to_type, from_name),
    )
    inserted = await conn.execute(
        """
        INSERT INTO forward_edge_messages (
            from_external_id, to_external_id, message_id, message_date, telegram_message_id
        )
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (from_external_id, to_external_id, message_id) DO NOTHING
        RETURNING message_id
        """,
        (from_peer_id, to_peer_id, message_uuid, message_date, telegram_message_id),
    )
    if await inserted.fetchone() is None:
        return False
    if bump_count:
        await conn.execute(
            """
            UPDATE forward_edges
            SET forward_count = forward_count + 1, last_seen_at = now()
            WHERE from_external_id = %s AND to_external_id = %s
            """,
            (from_peer_id, to_peer_id),
        )
    return True


async def recompute_forward_counts(conn: Any) -> None:
    await conn.execute(
        """
        UPDATE forward_edges e
        SET forward_count = COALESCE(s.n, 0)
        FROM (
            SELECT from_external_id, to_external_id, COUNT(*)::int AS n
            FROM forward_edge_messages
            GROUP BY from_external_id, to_external_id
        ) s
        WHERE e.from_external_id = s.from_external_id
          AND e.to_external_id = s.to_external_id
        """
    )


async def backfill_forward_tables(conn: Any) -> int:
    """Insert missing unique edges + fan-out from stored ``messages.fwd_from``."""
    rows = await conn.execute(
        """
        SELECT id, peer_external_id, telegram_message_id, date, fwd_from
        FROM messages
        WHERE fwd_from IS NOT NULL
          AND NOT EXISTS (
              SELECT 1
              FROM forward_edge_messages fem
              WHERE fem.message_id = messages.id
          )
        """
    )
    items = await rows.fetchall()
    inserted = 0
    for row in items:
        to_peer_id = signed_peer_from_fwd(row["fwd_from"])
        if to_peer_id is None:
            continue
        if await persist_forward_occurrence(
            conn,
            from_peer_id=int(row["peer_external_id"]),
            to_peer_id=to_peer_id,
            message_id=row["id"],
            message_date=row["date"],
            telegram_message_id=row.get("telegram_message_id"),
            from_name=fwd_from_name(row["fwd_from"]),
            bump_count=False,
        ):
            inserted += 1
    await recompute_forward_counts(conn)
    return inserted
