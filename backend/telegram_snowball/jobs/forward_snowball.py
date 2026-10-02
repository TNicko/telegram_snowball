from __future__ import annotations

import asyncio
import logging
from collections import deque
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from telethon import TelegramClient
from telethon.errors import ChannelPrivateError, ChatForbiddenError, FloodWaitError, UsernameNotOccupiedError
from telethon.tl.types import Message, PeerChannel, PeerChat, PeerUser

from telegram_snowball.catalog import _STORED_MEDIA_KIND_SQL
from telegram_snowball.config import Settings
from telegram_snowball.jobs.fetch_dialogues import _persist_message
from telegram_snowball.jobs.progress import (
    JobCancelled,
    await_unless_cancelled,
    mark_peer_idle,
    mark_peer_scraping,
    raise_if_cancelled,
    update_job_progress,
)
from telegram_snowball.telegram.client import telegram_client
from telegram_snowball.telegram.coverage import refresh_fetch_coverage, upsert_media_coverage
from telegram_snowball.telegram.forwards import fwd_from_name, persist_forward_occurrence, signed_peer_from_fwd
from telegram_snowball.telegram.first_message import ensure_first_visible_message
from telegram_snowball.telegram.history import chats_by_signed_id, get_history_page
from telegram_snowball.telegram.ids import (
    CHANNEL_MARK,
    channel_id_from_signed_peer_id,
    infer_peer_type_from_signed,
    input_peer_from_stored,
    is_snowball_target,
    to_signed_peer_id,
)
from telegram_snowball.telegram.image_blobs import harvest_message_image
from telegram_snowball.telegram.image_files import ImageUnavailable, persist_catalog_image
from telegram_snowball.telegram.materialize import (
    entity_label,
    materialize_peer,
    upsert_history_entities,
    upsert_peer,
    upsert_peer_stub,
)

lg = logging.getLogger(__name__)

_MEDIA_KINDS = ("image", "video", "gif", "audio", "document")
_RESOLVE_ERRORS = (
    ValueError,
    UsernameNotOccupiedError,
    ChannelPrivateError,
    ChatForbiddenError,
)


def _job_stats(peers_done: int, total_messages: int, media_counts: dict[str, int]) -> dict[str, int]:
    return {
        "peers": peers_done,
        "messages": total_messages,
        **{kind: int(media_counts.get(kind, 0) or 0) for kind in _MEDIA_KINDS},
    }


@dataclass(frozen=True, slots=True)
class FrontierItem:
    peer_id: int
    depth: int
    via_peer_id: int | None = None
    retry: bool = False


def _signed_from_peer(peer: Any) -> int | None:
    if peer is None:
        return None
    if isinstance(peer, PeerChannel):
        return -(CHANNEL_MARK + int(peer.channel_id))
    if isinstance(peer, PeerChat):
        return -int(peer.chat_id)
    if isinstance(peer, PeerUser):
        return int(peer.user_id)
    return to_signed_peer_id(peer)


def _signed_from_fwd(fwd: Any) -> int | None:
    return signed_peer_from_fwd(fwd)


def _fwd_from_name(fwd: Any) -> str | None:
    return fwd_from_name(fwd)


async def _load_peer(conn: Any, peer_id: int) -> dict[str, Any] | None:
    row = await conn.execute(
        "SELECT external_id, title, username, access_hash, peer_type FROM peers WHERE external_id = %s",
        (peer_id,),
    )
    found = await row.fetchone()
    return dict(found) if found is not None else None


async def find_forward_sample_message_id(
    conn: Any,
    *,
    via_peer_id: int,
    target_peer_id: int,
) -> int | None:
    """Recent message in ``via`` whose ``fwd_from`` points at ``target``."""
    raw_channel_id = channel_id_from_signed_peer_id(target_peer_id)
    if raw_channel_id is not None:
        row = await conn.execute(
            """
            SELECT telegram_message_id
            FROM messages
            WHERE peer_external_id = %s
              AND fwd_from IS NOT NULL
              AND (
                (
                  COALESCE(fwd_from->'from_id'->>'_', fwd_from->'from_id'->>'tl') = 'PeerChannel'
                  AND (fwd_from->'from_id'->>'channel_id') ~ '^[0-9]+$'
                  AND (fwd_from->'from_id'->>'channel_id')::bigint = %s
                )
                OR (
                  COALESCE(fwd_from->'saved_from_peer'->>'_', fwd_from->'saved_from_peer'->>'tl') = 'PeerChannel'
                  AND (fwd_from->'saved_from_peer'->>'channel_id') ~ '^[0-9]+$'
                  AND (fwd_from->'saved_from_peer'->>'channel_id')::bigint = %s
                )
              )
            ORDER BY date DESC NULLS LAST
            LIMIT 1
            """,
            (via_peer_id, raw_channel_id, raw_channel_id),
        )
    else:
        chat_tl_id = -target_peer_id if target_peer_id < 0 else target_peer_id
        row = await conn.execute(
            """
            SELECT telegram_message_id
            FROM messages
            WHERE peer_external_id = %s
              AND fwd_from IS NOT NULL
              AND (
                (
                  COALESCE(fwd_from->'from_id'->>'_', fwd_from->'from_id'->>'tl') = 'PeerChat'
                  AND (fwd_from->'from_id'->>'chat_id') ~ '^[0-9]+$'
                  AND (fwd_from->'from_id'->>'chat_id')::bigint = %s
                )
                OR (
                  COALESCE(fwd_from->'saved_from_peer'->>'_', fwd_from->'saved_from_peer'->>'tl') = 'PeerChat'
                  AND (fwd_from->'saved_from_peer'->>'chat_id') ~ '^[0-9]+$'
                  AND (fwd_from->'saved_from_peer'->>'chat_id')::bigint = %s
                )
              )
            ORDER BY date DESC NULLS LAST
            LIMIT 1
            """,
            (via_peer_id, chat_tl_id, chat_tl_id),
        )
    found = await row.fetchone()
    if found is None or found["telegram_message_id"] is None:
        return None
    return int(found["telegram_message_id"])


async def _seed_entity_cache_via_forward(
    client: TelegramClient,
    conn: Any,
    *,
    via_peer_id: int,
    target_peer_id: int,
) -> None:
    """Re-fetch a stored forward so Telethon caches the target's access_hash."""
    via = await _load_peer(conn, via_peer_id)
    if via is None:
        return
    via_entity = await _entity_from_row(client, via)
    if via_entity is None:
        return
    sample_mid = await find_forward_sample_message_id(
        conn,
        via_peer_id=via_peer_id,
        target_peer_id=target_peer_id,
    )
    if sample_mid is None:
        return
    try:
        await client.get_messages(via_entity, ids=sample_mid)
    except FloodWaitError:
        raise
    except Exception as err:
        lg.info(
            "via-forward seed failed via=%s target=%s mid=%s: %s",
            via_peer_id,
            target_peer_id,
            sample_mid,
            err,
        )


async def _entity_from_row(client: TelegramClient, peer: dict[str, Any]) -> Any | None:
    username = str(peer["username"]).strip() if peer.get("username") else ""
    if username:
        try:
            return await client.get_entity(username)
        except _RESOLVE_ERRORS as err:
            lg.info("username resolve failed @%s: %s", username, err)
        except FloodWaitError:
            raise
    input_peer = input_peer_from_stored(
        external_id=int(peer["external_id"]),
        peer_type=peer.get("peer_type"),
        access_hash=peer.get("access_hash"),
    )
    if input_peer is not None:
        try:
            return await client.get_entity(input_peer)
        except _RESOLVE_ERRORS as err:
            lg.info("input-peer resolve failed %s: %s", peer["external_id"], err)
        except FloodWaitError:
            raise
    return None


async def _resolve_scrape_entity(
    client: TelegramClient,
    conn: Any,
    *,
    peer_id: int,
    via_peer_id: int | None,
) -> Any | None:
    peer = await _load_peer(conn, peer_id)
    if peer is not None:
        entity = await _entity_from_row(client, peer)
        if entity is not None:
            return entity
    if via_peer_id is not None:
        await _seed_entity_cache_via_forward(
            client,
            conn,
            via_peer_id=via_peer_id,
            target_peer_id=peer_id,
        )
        try:
            return await client.get_entity(peer_id)
        except _RESOLVE_ERRORS as err:
            lg.info("via-forward get_entity failed %s: %s", peer_id, err)
        except FloodWaitError:
            raise
    try:
        return await client.get_entity(peer_id)
    except _RESOLVE_ERRORS as err:
        lg.info("cannot resolve %s: %s", peer_id, err)
        return None
    except FloodWaitError:
        raise


async def _enqueue_forward_source(
    conn: Any,
    *,
    src_peer_id: int,
    dst_peer_id: int,
    depth: int,
    from_name: str | None,
    chats_map: dict[int, Any],
    visited: set[int],
    pending: set[int],
    frontier: deque[FrontierItem],
) -> bool:
    if not is_snowball_target(dst_peer_id):
        return False
    entity = chats_map.get(dst_peer_id)
    if entity is not None:
        await upsert_peer(conn, entity=entity)
    else:
        await upsert_peer_stub(
            conn,
            external_id=dst_peer_id,
            peer_type=infer_peer_type_from_signed(dst_peer_id),
            title=from_name,
        )
    if dst_peer_id in visited or dst_peer_id in pending:
        return False
    pending.add(dst_peer_id)
    frontier.append(FrontierItem(dst_peer_id, depth + 1, src_peer_id))
    return True


async def _pop_frontier(
    conn: Any,
    frontier: deque[FrontierItem],
    *,
    use_scope: bool,
) -> FrontierItem:
    from telegram_snowball.scope.score import pick_frontier_index
    from telegram_snowball.scope.store import load_forward_scores

    items = list(frontier)
    need_scores = use_scope and not any(item.retry or item.depth == 0 for item in items)
    scores: dict[int, float] = {}
    if need_scores:
        scores = await load_forward_scores(conn, [item.peer_id for item in items])
    idx = pick_frontier_index(items, scores, use_scope=use_scope)
    item = items.pop(idx)
    frontier.clear()
    frontier.extend(items)
    return item


async def _harvest_image(
    client: TelegramClient,
    conn: Any,
    *,
    settings: Settings,
    message: Message,
    message_uuid: UUID,
    peer_id: int,
    stored_media: dict[str, Any] | None,
    persist: bool,
    job_id: UUID,
) -> None:
    for attempt in range(2):
        try:
            await harvest_message_image(
                client,
                conn,
                settings=settings,
                message=message,
                message_uuid=message_uuid,
                peer_id=peer_id,
                media=stored_media,
                persist=persist,
                job_id=job_id,
            )
            return
        except FloodWaitError as err:
            await await_unless_cancelled(
                conn,
                job_id,
                asyncio.sleep(int(getattr(err, "seconds", 1) or 1) + 1),
            )
            if attempt == 1:
                lg.warning("image harvest floodwait for peer %s msg %s", peer_id, message.id)


def _parse_max_depth(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def _has_image_phash(media: dict[str, Any] | None) -> bool:
    if not isinstance(media, dict):
        return False
    phash = media.get("phash")
    return isinstance(phash, str) and bool(phash.strip())


def _parse_job_datetime(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value).strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _message_in_date_range(
    message: Any,
    date_from: datetime | None,
    date_to: datetime | None,
) -> bool:
    if date_from is None and date_to is None:
        return True
    dt = _parse_job_datetime(getattr(message, "date", None))
    if dt is None:
        return False
    if date_from is not None and dt < date_from:
        return False
    if date_to is not None and dt > date_to:
        return False
    return True


async def _stored_message_id_span(conn: Any, peer_id: int) -> tuple[int | None, int | None]:
    row = await conn.execute(
        """
        SELECT MIN(telegram_message_id) AS lo, MAX(telegram_message_id) AS hi
        FROM messages
        WHERE peer_external_id = %s
          AND telegram_message_id IS DISTINCT FROM (
              SELECT first_message_id FROM peers WHERE external_id = %s
          )
        """,
        (peer_id, peer_id),
    )
    data = await row.fetchone()
    if data is None:
        return None, None
    lo, hi = data["lo"], data["hi"]
    return (int(lo) if lo is not None else None, int(hi) if hi is not None else None)


_BACKFILL_ID_BATCH = 80


async def _unpersisted_image_phashes(conn: Any, peer_id: int) -> list[str]:
    rows = await conn.execute(
        """
        SELECT DISTINCT ibm.phash
        FROM image_blob_messages ibm
        JOIN image_blobs b ON b.phash = ibm.phash
        WHERE ibm.peer_external_id = %s
          AND NULLIF(b.canonical_path, '') IS NULL
        ORDER BY ibm.phash
        """,
        (peer_id,),
    )
    return [str(row["phash"]) for row in await rows.fetchall() if row["phash"]]


async def _image_messages_missing_phash(conn: Any, peer_id: int) -> list[dict[str, Any]]:
    kind = _STORED_MEDIA_KIND_SQL.strip()
    rows = await conn.execute(
        f"""
        SELECT id, telegram_message_id, media
        FROM messages
        WHERE peer_external_id = %s
          AND telegram_message_id IS NOT NULL
          AND ({kind}) = 'image'
          AND COALESCE(NULLIF(BTRIM(media->>'phash'), ''), '') = ''
        ORDER BY telegram_message_id DESC
        """,
        (peer_id,),
    )
    return [dict(row) for row in await rows.fetchall()]


def _as_message_list(got: Any) -> list[Any]:
    if got is None:
        return []
    if isinstance(got, list):
        return got
    return [got]


async def _persist_remaining_images(
    client: TelegramClient,
    conn: Any,
    *,
    settings: Settings,
    job_id: UUID,
    peer_id: int,
    label: str,
) -> int:
    persisted = 0
    hashes = await _unpersisted_image_phashes(conn, peer_id)
    total = len(hashes)
    for index, phash in enumerate(hashes, start=1):
        await raise_if_cancelled(conn, job_id)
        try:
            await persist_catalog_image(
                conn,
                settings,
                phash,
                allow_telegram=True,
                client=client,
                job_id=job_id,
            )
            persisted += 1
        except FloodWaitError as err:
            await await_unless_cancelled(
                conn, job_id, asyncio.sleep(int(getattr(err, "seconds", 1) or 1) + 1)
            )
            try:
                await persist_catalog_image(
                    conn,
                    settings,
                    phash,
                    allow_telegram=True,
                    client=client,
                    job_id=job_id,
                )
                persisted += 1
            except JobCancelled:
                raise
            except (FloodWaitError, ImageUnavailable, Exception) as retry_err:
                lg.info("image persist remainder skip %s: %s", phash, retry_err)
        except JobCancelled:
            raise
        except ImageUnavailable as err:
            lg.info("image persist remainder skip %s: %s", phash, err)
        except Exception as err:
            lg.info("image persist remainder failed %s: %s", phash, err)
        if index == 1 or index == total or index % 10 == 0:
            await update_job_progress(
                conn,
                job_id,
                {
                    "phase": "scrape",
                    "current_peer": peer_id,
                    "current_label": label,
                    "detail": f"Downloading remaining images ({index}/{total})",
                },
            )
            await conn.commit()
    return persisted


async def _hash_remaining_images(
    client: TelegramClient,
    conn: Any,
    *,
    settings: Settings,
    job_id: UUID,
    peer_id: int,
    entity: Any,
    label: str,
    persist: bool,
) -> int:
    missing = await _image_messages_missing_phash(conn, peer_id)
    harvested = 0
    for start in range(0, len(missing), _BACKFILL_ID_BATCH):
        await raise_if_cancelled(conn, job_id)
        chunk = missing[start : start + _BACKFILL_ID_BATCH]
        ids = [int(row["telegram_message_id"]) for row in chunk]
        by_id = {int(row["telegram_message_id"]): row for row in chunk}
        try:
            got = await await_unless_cancelled(
                conn, job_id, client.get_messages(entity, ids=ids)
            )
        except FloodWaitError as err:
            await await_unless_cancelled(
                conn, job_id, asyncio.sleep(int(getattr(err, "seconds", 1) or 1) + 1)
            )
            try:
                got = await await_unless_cancelled(
                    conn, job_id, client.get_messages(entity, ids=ids)
                )
            except JobCancelled:
                raise
            except Exception as retry_err:
                lg.info("image remainder get_messages failed peer %s: %s", peer_id, retry_err)
                continue
        except JobCancelled:
            raise
        except Exception as err:
            lg.info("image remainder get_messages failed peer %s: %s", peer_id, err)
            continue
        for message in _as_message_list(got):
            if not isinstance(message, Message):
                continue
            mid = getattr(message, "id", None)
            if not isinstance(mid, int):
                continue
            stored = by_id.get(mid)
            if stored is None:
                continue
            await _harvest_image(
                client,
                conn,
                settings=settings,
                message=message,
                message_uuid=stored["id"],
                peer_id=peer_id,
                stored_media=stored.get("media") if isinstance(stored.get("media"), dict) else None,
                persist=persist,
                job_id=job_id,
            )
            harvested += 1
        done = min(start + len(chunk), len(missing))
        await update_job_progress(
            conn,
            job_id,
            {
                "phase": "scrape",
                "current_peer": peer_id,
                "current_label": label,
                "detail": f"Hashing remaining images ({done}/{len(missing)})",
            },
        )
        await conn.commit()
    return harvested


async def run_forward_snowball(
    conn: Any,
    *,
    settings: Settings,
    job_id: UUID,
    params: dict[str, Any],
) -> None:
    seed = int(params["seed_external_id"])
    max_depth_i = _parse_max_depth(params.get("max_depth"))
    include_images = bool(params.get("images", False))
    include_videos = bool(params.get("videos", False))
    embed_images = bool(params.get("embed_images", True))
    embed_text = bool(params.get("embed_text", True))
    use_scope = bool(params.get("use_scope", False)) and embed_images
    fill_remaining = bool(params.get("fill_remaining", False))
    remainder = str(params.get("remainder") or "")
    date_from = _parse_job_datetime(params.get("date_from"))
    date_to = _parse_job_datetime(params.get("date_to"))
    skip_history = fill_remaining and remainder in {"image", "image_phash", "image_download"}

    await update_job_progress(
        conn,
        job_id,
        {
            "phase": "start",
            "seed_external_id": seed,
            "embed_images": embed_images,
            "embed_text": embed_text,
            "use_scope": use_scope,
            "detail": "Opening Telegram session",
        },
    )

    visited: set[int] = set()
    pending: set[int] = {seed}
    visited_ids: list[int] = []
    frontier: deque[FrontierItem] = deque([FrontierItem(seed, 0)])
    peers_done = 0
    total_messages = 0
    media_counts: dict[str, int] = {"image": 0, "video": 0, "gif": 0, "audio": 0, "document": 0}

    async with telegram_client(settings) as client:
        while frontier:
            await raise_if_cancelled(conn, job_id)
            item = await _pop_frontier(conn, frontier, use_scope=use_scope)
            peer_id, depth, via_peer_id = item.peer_id, item.depth, item.via_peer_id
            pending.discard(peer_id)
            if peer_id in visited:
                continue
            if max_depth_i is not None and depth > max_depth_i:
                continue
            visited.add(peer_id)

            peer = await _load_peer(conn, peer_id)
            label = (peer["title"] or peer["username"] or str(peer_id)) if peer else str(peer_id)
            if peer is not None:
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

            try:
                entity = await _resolve_scrape_entity(
                    client,
                    conn,
                    peer_id=peer_id,
                    via_peer_id=via_peer_id,
                )
            except FloodWaitError as err:
                await asyncio.sleep(int(err.seconds) + 1)
                pending.add(peer_id)
                frontier.appendleft(replace(item, retry=True))
                visited.discard(peer_id)
                continue

            if entity is None:
                if peer is not None:
                    await mark_peer_idle(conn, peer_id)
                    await conn.commit()
                await update_job_progress(
                    conn,
                    job_id,
                    {"warnings": [f"Peer {peer_id} is inaccessible; skipped"]},
                )
                continue

            await upsert_peer(conn, entity=entity)
            try:
                await materialize_peer(
                    client,
                    conn,
                    settings=settings,
                    entity=entity,
                    materialize_linked=False,
                    fetch_first_message=False,
                )
            except FloodWaitError as err:
                await asyncio.sleep(int(err.seconds) + 1)
                pending.add(peer_id)
                frontier.appendleft(replace(item, retry=True))
                visited.discard(peer_id)
                continue

            label = entity_label(entity)
            await mark_peer_scraping(conn, peer_id, detail="Finding first message")
            try:
                await ensure_first_visible_message(client, conn, entity=entity, peer_id=peer_id)
                await conn.commit()
            except FloodWaitError as err:
                await asyncio.sleep(int(err.seconds) + 1)
                try:
                    await ensure_first_visible_message(client, conn, entity=entity, peer_id=peer_id)
                    await conn.commit()
                except (FloodWaitError, ChannelPrivateError, ChatForbiddenError):
                    pass
            except (ChannelPrivateError, ChatForbiddenError):
                pass

            await mark_peer_scraping(conn, peer_id, detail="Resolving")
            visited_ids.append(peer_id)
            messages_scraped = 0
            oldest_stored, newest_stored = await _stored_message_id_span(conn, peer_id)
            walk_oldest_id: int | None = None

            async def walk_history(*, start_offset_id: int, min_id: int) -> None:
                nonlocal messages_scraped, total_messages, walk_oldest_id
                offset_id = start_offset_id
                while True:
                    try:
                        page = await await_unless_cancelled(
                            conn,
                            job_id,
                            get_history_page(client, entity, offset_id=offset_id, min_id=min_id),
                        )
                    except FloodWaitError as err:
                        await await_unless_cancelled(
                            conn, job_id, asyncio.sleep(int(err.seconds) + 1)
                        )
                        continue
                    if not page.messages:
                        break

                    await upsert_history_entities(conn, chats=page.chats, users=page.users)
                    chats_map = chats_by_signed_id(page.chats)
                    min_id_seen: int | None = None
                    new_sources = 0
                    page_new = 0
                    for message in page.messages:
                        if not isinstance(message, Message):
                            continue
                        mid = getattr(message, "id", None)
                        if isinstance(mid, int):
                            min_id_seen = mid if min_id_seen is None else min(min_id_seen, mid)
                            if min_id and mid <= min_id:
                                continue
                        persisted = await _persist_message(conn, peer_id=peer_id, message=message)
                        if persisted is None:
                            continue
                        message_uuid, kind, stored_media, inserted = persisted
                        need_harvest = kind == "image" and (
                            inserted or not _has_image_phash(stored_media)
                        )
                        if not inserted and not need_harvest:
                            continue
                        if inserted:
                            page_new += 1
                            messages_scraped += 1
                            total_messages += 1
                            if kind in media_counts:
                                media_counts[kind] += 1
                        if need_harvest and _message_in_date_range(message, date_from, date_to):
                            await _harvest_image(
                                client,
                                conn,
                                settings=settings,
                                message=message,
                                message_uuid=message_uuid,
                                peer_id=peer_id,
                                stored_media=stored_media,
                                persist=include_images,
                                job_id=job_id,
                            )
                        if not inserted:
                            continue
                        src = _signed_from_fwd(message.fwd_from)
                        if src is not None:
                            await persist_forward_occurrence(
                                conn,
                                from_peer_id=peer_id,
                                to_peer_id=src,
                                message_id=message_uuid,
                                message_date=getattr(message, "date", None),
                                telegram_message_id=int(message.id) if getattr(message, "id", None) else None,
                                from_name=_fwd_from_name(message.fwd_from),
                            )
                            added = await _enqueue_forward_source(
                                conn,
                                src_peer_id=peer_id,
                                dst_peer_id=src,
                                depth=depth,
                                from_name=_fwd_from_name(message.fwd_from),
                                chats_map=chats_map,
                                visited=visited,
                                pending=pending,
                                frontier=frontier,
                            )
                            if added:
                                new_sources += 1

                    if new_sources:
                        lg.info(
                            "Enqueued %s new forward source(s) from %s (frontier=%s)",
                            new_sources,
                            peer_id,
                            len(frontier),
                        )
                    if min_id_seen is not None:
                        walk_oldest_id = (
                            min_id_seen
                            if walk_oldest_id is None
                            else min(walk_oldest_id, min_id_seen)
                        )
                    await mark_peer_scraping(
                        conn,
                        peer_id,
                        detail=f"Fetching messages ({messages_scraped})",
                        messages_scraped=messages_scraped,
                    )
                    await refresh_fetch_coverage(
                        conn, peer_id, min_telegram_id=walk_oldest_id
                    )
                    await update_job_progress(
                        conn,
                        job_id,
                        {
                            "phase": "scrape",
                            "messages_scraped": total_messages,
                            "current_peer": peer_id,
                            "current_label": label,
                            "frontier": len(frontier),
                            "stats": _job_stats(peers_done, total_messages, media_counts),
                            "detail": f"Scraping {label} · {messages_scraped} messages",
                        },
                    )
                    await conn.commit()
                    if min_id_seen is None or (offset_id and min_id_seen >= offset_id):
                        break
                    if page_new == 0 and min_id:
                        break
                    offset_id = min_id_seen

            if not skip_history:
                try:
                    if newest_stored:
                        await walk_history(start_offset_id=0, min_id=newest_stored)
                    await walk_history(start_offset_id=oldest_stored or 0, min_id=0)
                except (ChannelPrivateError, ChatForbiddenError) as err:
                    lg.info("history forbidden for %s: %s", peer_id, err)
                except JobCancelled:
                    await mark_peer_idle(conn, peer_id)
                    await conn.commit()
                    raise

                if walk_oldest_id is not None:
                    await refresh_fetch_coverage(conn, peer_id, min_telegram_id=walk_oldest_id)
                if messages_scraped > 0 or newest_stored is not None:
                    await upsert_media_coverage(
                        conn,
                        peer_id,
                        videos_excluded=not include_videos,
                    )

            persist_remaining = fill_remaining and (
                remainder == "image_download"
                or (include_images and remainder in {"", "image", "all"})
            )
            hash_remaining = fill_remaining and remainder in {"image", "image_phash", "all"}
            if persist_remaining or hash_remaining:
                if persist_remaining:
                    await mark_peer_scraping(conn, peer_id, detail="Downloading remaining images")
                    await _persist_remaining_images(
                        client,
                        conn,
                        settings=settings,
                        job_id=job_id,
                        peer_id=peer_id,
                        label=label,
                    )
                if hash_remaining:
                    await mark_peer_scraping(conn, peer_id, detail="Hashing remaining images")
                    await _hash_remaining_images(
                        client,
                        conn,
                        settings=settings,
                        job_id=job_id,
                        peer_id=peer_id,
                        entity=entity,
                        label=label,
                        persist=include_images and remainder != "image_phash",
                    )
                await upsert_media_coverage(
                    conn,
                    peer_id,
                    videos_excluded=not include_videos,
                )

            await conn.execute(
                """
                UPDATE peers
                SET messages_scraped = GREATEST(
                        messages_scraped,
                        COALESCE((SELECT posts FROM peer_counts WHERE peer_external_id = %s), 0)
                    ),
                    is_scraping = false,
                    scrape_detail = NULL,
                    updated_at = now()
                WHERE external_id = %s
                """,
                (peer_id, peer_id),
            )
            peers_done += 1
            await conn.commit()
            await mark_peer_idle(conn, peer_id)
            if embed_text or embed_images:
                await raise_if_cancelled(conn, job_id)
                await update_job_progress(
                    conn,
                    job_id,
                    {
                        "peers_done": peers_done,
                        "messages_scraped": total_messages,
                        "visited_peer_ids": visited_ids,
                        "frontier": len(frontier),
                        "stats": _job_stats(peers_done, total_messages, media_counts),
                        "detail": f"Embedding {entity_label(entity)}",
                    },
                )
                from telegram_snowball.embed.client import EmbedUnavailable, embed_peer
                from telegram_snowball.embed.runtime import EncoderError

                try:
                    await embed_peer(
                        settings,
                        job_id=job_id,
                        peer_external_id=peer_id,
                        text=embed_text,
                        images=embed_images,
                    )
                except EncoderError as exc:
                    raise RuntimeError(str(exc)) from exc
                except EmbedUnavailable as exc:
                    raise RuntimeError(str(exc)) from exc
            if use_scope and embed_images:
                from telegram_snowball.scope.update import score_after_peer_embed

                await raise_if_cancelled(conn, job_id)
                scored = await score_after_peer_embed(conn, peer_external_id=peer_id)
                await conn.commit()
                lg.info(
                    "scope scored peer %s images=%s origins=%s frontier=%s",
                    peer_id,
                    scored.get("images"),
                    scored.get("origins"),
                    len(frontier),
                )
            await update_job_progress(
                conn,
                job_id,
                {
                    "peers_done": peers_done,
                    "messages_scraped": total_messages,
                    "visited_peer_ids": visited_ids,
                    "frontier": len(frontier),
                    "stats": _job_stats(peers_done, total_messages, media_counts),
                    "detail": f"Finished {entity_label(entity)}",
                    "media_note": (
                        "Video download follows in a later pass" if include_videos else None
                    ),
                },
            )

    await update_job_progress(
        conn,
        job_id,
        {
            "phase": "done",
            "peers_done": peers_done,
            "messages_scraped": total_messages,
            "visited_peer_ids": visited_ids,
            "stats": _job_stats(peers_done, total_messages, media_counts),
            "detail": f"Finished ({peers_done} peer{'s' if peers_done != 1 else ''})",
        },
    )
