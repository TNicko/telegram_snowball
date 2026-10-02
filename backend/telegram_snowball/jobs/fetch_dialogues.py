from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from psycopg.types.json import Jsonb
from telethon.errors import ChannelPrivateError, ChatForbiddenError, FloodWaitError
from telethon.tl.types import Message, MessageService

from telegram_snowball.config import Settings
from telegram_snowball.jobs.progress import raise_if_cancelled, update_job_progress
from telegram_snowball.jsonutil import json_safe
from telegram_snowball.telegram.client import telegram_client
from telegram_snowball.telegram.coverage import refresh_fetch_coverage
from telegram_snowball.telegram.ids import to_signed_peer_id
from telegram_snowball.telegram.materialize import entity_label, materialize_peer, refresh_connected_account
from telegram_snowball.telegram.media_kinds import classify_message_media, media_kind_from_stored

lg = logging.getLogger(__name__)


async def _sleep_flood(err: FloodWaitError) -> None:
    import asyncio

    seconds = int(getattr(err, "seconds", 1) or 1)
    lg.warning("FloodWait %ss", seconds)
    await asyncio.sleep(seconds + 1)


async def _persist_message(
    conn: Any, *, peer_id: int, message: Message | MessageService
) -> tuple[UUID, str, dict[str, Any] | None, bool] | None:
    """Store a message. Returns (id, media kind, stored media, inserted) or None if skipped."""
    if not getattr(message, "id", None):
        return None
    date = getattr(message, "date", None)
    content = getattr(message, "message", None) or None
    from_id = to_signed_peer_id(getattr(message, "from_id", None) or getattr(message, "sender_id", None))
    fwd = None
    if getattr(message, "fwd_from", None) is not None:
        fwd = message.fwd_from.to_dict()
    media = classify_message_media(getattr(message, "media", None))
    row = await conn.execute(
        """
        INSERT INTO messages (
            peer_external_id, telegram_message_id, date, content,
            from_external_id, fwd_from, media
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (peer_external_id, telegram_message_id) DO UPDATE SET
            content = EXCLUDED.content,
            fwd_from = COALESCE(EXCLUDED.fwd_from, messages.fwd_from),
            media = jsonb_set(
                COALESCE(EXCLUDED.media, '{}'::jsonb)
                    || COALESCE(messages.media, '{}'::jsonb),
                '{kind}',
                COALESCE(EXCLUDED.media->'kind', messages.media->'kind')
            )
        RETURNING id, media, (xmax = 0) AS inserted
        """,
        (
            peer_id,
            int(message.id),
            date,
            content,
            from_id,
            Jsonb(json_safe(fwd)) if fwd is not None else None,
            Jsonb(json_safe(media)) if media is not None else None,
        ),
    )
    stored = await row.fetchone()
    if stored is None:
        return None
    stored_media = stored["media"] if isinstance(stored["media"], dict) else media
    kind = media_kind_from_stored(stored_media) or ""
    inserted = bool(stored["inserted"])
    if inserted:
        from telegram_snowball.peer_counts import bump_peer_counts, message_insert_deltas

        downloaded = False
        if isinstance(stored_media, dict):
            downloaded = stored_media.get("downloaded") in (True, "true", "t", "1", 1)
        await bump_peer_counts(
            conn,
            peer_id,
            message_insert_deltas(content=content, kind=kind, downloaded=downloaded),
        )
    return stored["id"], kind, stored_media, inserted


async def run_fetch_dialogues(
    conn: Any,
    *,
    settings: Settings,
    job_id: UUID,
    params: dict[str, Any],
) -> None:
    """Default: materialize dialogue peers (full + profile photo). Messages are opt-in."""
    include_messages = bool(params.get("messages", False))
    seen = 0
    materialized = 0

    await update_job_progress(
        conn,
        job_id,
        {
            "phase": "dialogues",
            "mode": "materialize",
            "detail": "Listing account dialogues",
            "dialogues_seen": 0,
            "dialogues_materialized": 0,
        },
    )

    async with telegram_client(settings) as client:
        try:
            await refresh_connected_account(client, conn, settings=settings)
            await conn.commit()
        except FloodWaitError as err:
            await _sleep_flood(err)
        async for dialog in client.iter_dialogs(ignore_migrated=True):
            await raise_if_cancelled(conn, job_id)
            entity = dialog.entity
            seen += 1
            try:
                signed = await materialize_peer(
                    client,
                    conn,
                    settings=settings,
                    entity=entity,
                    materialize_linked=True,
                )
            except FloodWaitError as err:
                await _sleep_flood(err)
                signed = await materialize_peer(
                    client,
                    conn,
                    settings=settings,
                    entity=entity,
                    materialize_linked=True,
                )
            if signed is None:
                await conn.commit()
                continue
            materialized += 1
            label = entity_label(entity)

            if include_messages:
                try:
                    async for message in client.iter_messages(entity):
                        if not isinstance(message, Message):
                            continue
                        await _persist_message(conn, peer_id=signed, message=message)
                except FloodWaitError as err:
                    await _sleep_flood(err)
                except (ChannelPrivateError, ChatForbiddenError) as err:
                    lg.info("skip messages for %s: %s", signed, err)
                await refresh_fetch_coverage(conn, signed)

            await conn.commit()
            await update_job_progress(
                conn,
                job_id,
                {
                    "phase": "dialogues",
                    "dialogues_seen": seen,
                    "dialogues_materialized": materialized,
                    "current_peer": signed,
                    "current_label": label,
                    "detail": f"Loaded {materialized} dialogues",
                },
            )

    await update_job_progress(
        conn,
        job_id,
        {
            "phase": "done",
            "dialogues_seen": seen,
            "dialogues_materialized": materialized,
            "detail": f"Loaded {materialized} dialogues",
        },
    )
