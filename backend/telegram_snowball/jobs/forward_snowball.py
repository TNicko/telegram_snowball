from __future__ import annotations

import logging
from collections import deque
from typing import Any
from uuid import UUID

from telethon.errors import ChannelPrivateError, ChatForbiddenError, FloodWaitError, UsernameNotOccupiedError
from telethon.tl.types import Message, PeerChannel, PeerChat, PeerUser

from telegram_snowball.config import Settings
from telegram_snowball.jobs.progress import mark_peer_idle, mark_peer_scraping, update_job_progress
from telegram_snowball.telegram.client import telegram_client
from telegram_snowball.telegram.ids import CHANNEL_MARK, to_signed_peer_id
from telegram_snowball.telegram.coverage import refresh_fetch_coverage
from telegram_snowball.telegram.materialize import entity_label, upsert_peer

lg = logging.getLogger(__name__)


def _signed_from_fwd(fwd: Any) -> int | None:
    if fwd is None:
        return None
    from_id = getattr(fwd, "from_id", None)
    if isinstance(from_id, PeerChannel):
        return -(CHANNEL_MARK + int(from_id.channel_id))
    if isinstance(from_id, PeerChat):
        return -int(from_id.chat_id)
    if isinstance(from_id, PeerUser):
        return int(from_id.user_id)
    return to_signed_peer_id(from_id)


async def _upsert_forward_edge(conn: Any, *, src: int, dst: int) -> None:
    if src == dst:
        return
    await conn.execute(
        """
        INSERT INTO forward_edges (from_external_id, to_external_id, forward_count, last_seen_at)
        VALUES (%s, %s, 1, now())
        ON CONFLICT (from_external_id, to_external_id) DO UPDATE SET
            forward_count = forward_edges.forward_count + 1,
            last_seen_at = now()
        """,
        (src, dst),
    )


async def run_forward_snowball(
    conn: Any,
    *,
    settings: Settings,
    job_id: UUID,
    params: dict[str, Any],
) -> None:
    seed = int(params["seed_external_id"])
    max_depth = params.get("max_depth")
    max_depth_i = int(max_depth) if max_depth not in (None, "", 0) else None
    include_images = bool(params.get("images", True))
    include_videos = bool(params.get("videos", True))
    embed_images = bool(params.get("embed_images", True))
    embed_text = bool(params.get("embed_text", True))

    await update_job_progress(
        conn,
        job_id,
        {
            "phase": "start",
            "seed_external_id": seed,
            "embed_images": embed_images,
            "embed_text": embed_text,
            "detail": "Opening Telegram session",
        },
    )

    visited: set[int] = set()
    frontier: deque[tuple[int, int]] = deque([(seed, 0)])
    peers_done = 0

    async with telegram_client(settings) as client:
        while frontier:
            peer_id, depth = frontier.popleft()
            if peer_id in visited:
                continue
            if max_depth_i is not None and depth > max_depth_i:
                continue
            visited.add(peer_id)

            row = await conn.execute(
                "SELECT external_id, title, username, access_hash, peer_type FROM peers WHERE external_id = %s",
                (peer_id,),
            )
            peer = await row.fetchone()
            if peer is None:
                await update_job_progress(
                    conn,
                    job_id,
                    {
                        "warnings": [f"Peer {peer_id} is not in the local catalog; skipped"],
                    },
                )
                continue

            label = peer["title"] or peer["username"] or str(peer_id)
            await mark_peer_scraping(conn, peer_id, detail="Resolving")
            await update_job_progress(
                conn,
                job_id,
                {
                    "phase": "scrape",
                    "current_peer": peer_id,
                    "current_label": label,
                    "current_depth": depth,
                    "peers_done": peers_done,
                    "frontier": len(frontier),
                    "detail": f"Scraping {label}",
                },
            )
            await conn.commit()

            entity = None
            try:
                if peer["username"]:
                    entity = await client.get_entity(peer["username"])
                else:
                    entity = await client.get_entity(peer_id)
            except (ValueError, UsernameNotOccupiedError, ChannelPrivateError, ChatForbiddenError) as err:
                lg.info("cannot resolve %s: %s", peer_id, err)
                await mark_peer_idle(conn, peer_id)
                await conn.commit()
                continue
            except FloodWaitError as err:
                import asyncio

                await asyncio.sleep(int(err.seconds) + 1)
                frontier.appendleft((peer_id, depth))
                visited.discard(peer_id)
                continue

            await upsert_peer(conn, entity=entity)
            messages_scraped = 0
            try:
                async for message in client.iter_messages(entity):
                    if not isinstance(message, Message):
                        continue
                    from telegram_snowball.jobs.fetch_dialogues import _persist_message

                    await _persist_message(conn, peer_id=peer_id, message=message)
                    messages_scraped += 1
                    src = _signed_from_fwd(message.fwd_from)
                    if src is not None:
                        await _upsert_forward_edge(conn, src=peer_id, dst=src)
                        if src not in visited:
                            frontier.append((src, depth + 1))
                    if messages_scraped % 50 == 0:
                        await mark_peer_scraping(
                            conn,
                            peer_id,
                            detail=f"Fetching messages ({messages_scraped})",
                            messages_scraped=messages_scraped,
                        )
                        await update_job_progress(
                            conn,
                            job_id,
                            {
                                "messages_scraped": messages_scraped,
                                "current_peer": peer_id,
                                "current_label": label,
                            },
                        )
                        await conn.commit()
            except (ChannelPrivateError, ChatForbiddenError) as err:
                lg.info("history forbidden for %s: %s", peer_id, err)

            if messages_scraped > 0:
                await refresh_fetch_coverage(conn, peer_id)

            await conn.execute(
                """
                UPDATE peers
                SET messages_scraped = GREATEST(messages_scraped, %s),
                    is_scraping = false,
                    scrape_detail = NULL,
                    updated_at = now()
                WHERE external_id = %s
                """,
                (messages_scraped, peer_id),
            )
            peers_done += 1
            await conn.commit()
            await mark_peer_idle(conn, peer_id)
            await update_job_progress(
                conn,
                job_id,
                {
                    "peers_done": peers_done,
                    "messages_scraped": messages_scraped,
                    "detail": f"Finished {entity_label(entity)}",
                    "media_note": (
                        "Media download/embed follow in a later pass"
                        if (include_images or include_videos or embed_images or embed_text)
                        else None
                    ),
                },
            )

    await update_job_progress(
        conn,
        job_id,
        {"phase": "done", "peers_done": peers_done, "detail": f"Snowball finished ({peers_done} peers)"},
    )
