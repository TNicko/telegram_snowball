"""Embed pending message text and image blobs with the selected local models."""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from telegram_snowball.config import Settings
from telegram_snowball.embed.runtime import EncoderError, load_encoder
from telegram_snowball.embed.store import (
    pending_image_phashes,
    pending_text_rows,
    upsert_image_embedding,
    upsert_text_embedding,
)
from telegram_snowball.jobs.progress import raise_if_cancelled, update_job_progress
from telegram_snowball.telegram.image_files import image_bytes_on_disk

lg = logging.getLogger(__name__)

TEXT_BATCH = 16
IMAGE_BATCH = 4


async def embed_pending_text(
    conn: Any,
    settings: Settings,
    *,
    job_id: UUID | None = None,
    peer_external_id: int | None = None,
) -> int:
    encoder = load_encoder(settings, "text")
    done = 0
    while True:
        if job_id is not None:
            await raise_if_cancelled(conn, job_id)
        rows = await pending_text_rows(
            conn,
            peer_external_id=peer_external_id,
            model_id=encoder.model_id,
            limit=TEXT_BATCH,
        )
        if not rows:
            return done
        texts = [str(row["content"]).strip() for row in rows]
        vectors = encoder.encode_texts(texts, is_query=False)
        for row, values in zip(rows, vectors, strict=True):
            await upsert_text_embedding(
                conn,
                message_id=row["id"],
                model_id=encoder.model_id,
                values=values,
            )
        done += len(rows)
        await conn.commit()
        if job_id is not None:
            await update_job_progress(
                conn,
                job_id,
                {"detail": f"Embedded {done} messages", "text_done": done, "phase": "embed_text"},
            )
        if len(rows) < TEXT_BATCH:
            return done


async def embed_pending_images(
    conn: Any,
    settings: Settings,
    *,
    job_id: UUID | None = None,
    peer_external_id: int | None = None,
) -> tuple[int, int]:
    encoder = load_encoder(settings, "image")
    done = 0
    skipped = 0
    missing: set[str] = set()
    while True:
        if job_id is not None:
            await raise_if_cancelled(conn, job_id)
        phashes = await pending_image_phashes(
            conn,
            peer_external_id=peer_external_id,
            model_id=encoder.model_id,
            limit=IMAGE_BATCH * 4,
            exclude=list(missing),
        )
        if not phashes:
            return done, skipped
        batch_ids: list[str] = []
        batch_bytes: list[bytes] = []
        for phash in phashes:
            payload = await image_bytes_on_disk(conn, settings, phash)
            if not payload:
                skipped += 1
                missing.add(phash)
                continue
            batch_ids.append(phash)
            batch_bytes.append(payload)
            if len(batch_ids) >= IMAGE_BATCH:
                break
        if not batch_ids:
            if len(phashes) < IMAGE_BATCH * 4:
                return done, skipped
            continue
        vectors = encoder.encode_images(batch_bytes)
        for phash, values in zip(batch_ids, vectors, strict=True):
            await upsert_image_embedding(
                conn,
                phash=phash,
                model_id=encoder.model_id,
                values=values,
            )
        done += len(batch_ids)
        await conn.commit()
        if job_id is not None:
            await update_job_progress(
                conn,
                job_id,
                {
                    "detail": f"Embedded {done} images",
                    "image_done": done,
                    "image_skipped": skipped,
                    "phase": "embed_images",
                },
            )
        if len(phashes) < IMAGE_BATCH * 4 and len(batch_ids) < IMAGE_BATCH:
            return done, skipped


async def embed_peer_pending(
    conn: Any,
    settings: Settings,
    *,
    job_id: UUID | None,
    peer_external_id: int,
    text: bool,
    images: bool,
) -> None:
    if text:
        await embed_pending_text(
            conn, settings, job_id=job_id, peer_external_id=peer_external_id
        )
    if images:
        await embed_pending_images(
            conn, settings, job_id=job_id, peer_external_id=peer_external_id
        )


async def run_embed(
    conn: Any,
    *,
    settings: Settings,
    job_id: UUID,
    params: dict[str, Any],
) -> None:
    targets = params.get("targets") or ["text", "images"]
    if isinstance(targets, str):
        targets = [targets]
    want_text = "text" in targets
    want_images = "images" in targets or "image" in targets
    peer_raw = params.get("peer_external_id")
    peer_id: int | None
    try:
        peer_id = int(peer_raw) if peer_raw is not None and peer_raw != "" else None
    except (TypeError, ValueError):
        peer_id = None
    await update_job_progress(
        conn,
        job_id,
        {"phase": "embed", "detail": "Loading embedding models", "peer_external_id": peer_id},
    )
    text_done = 0
    image_done = 0
    image_skipped = 0
    try:
        if want_text:
            text_done = await embed_pending_text(
                conn, settings, job_id=job_id, peer_external_id=peer_id
            )
        if want_images:
            image_done, image_skipped = await embed_pending_images(
                conn, settings, job_id=job_id, peer_external_id=peer_id
            )
    except EncoderError:
        raise
    detail = []
    if want_text:
        detail.append(f"{text_done} messages")
    if want_images:
        detail.append(f"{image_done} images")
        if image_skipped:
            detail.append(f"{image_skipped} images skipped (no file on disk)")
    await update_job_progress(
        conn,
        job_id,
        {
            "phase": "done",
            "detail": "Embedded " + ", ".join(detail) if detail else "Nothing to embed",
            "text_done": text_done,
            "image_done": image_done,
            "image_skipped": image_skipped,
        },
    )
