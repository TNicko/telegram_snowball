"""Semantic search over stored text and image embeddings."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from telegram_snowball.api.routes.images import _attach_image_peers
from telegram_snowball.api.routes.messages import _MESSAGE_PEER_COLUMNS, _public_message
from telegram_snowball.config import load_settings
from telegram_snowball.db import get_conn
from telegram_snowball.embed.client import EmbedUnavailable, encode_texts
from telegram_snowball.embed.runtime import EncoderError, vision_is_multimodal
from telegram_snowball.embed.store import search_image_blobs, search_text_messages
from telegram_snowball.models_catalog import load_selection, model_is_ready

router = APIRouter()


def _score(row: dict[str, Any]) -> float | None:
    raw = row.get("score")
    try:
        return round(float(raw), 4)
    except (TypeError, ValueError):
        return None


@router.get("/search/messages")
async def search_messages(
    q: str = Query(..., min_length=1),
    limit: int = Query(default=50, ge=1, le=200),
    peer_external_id: int | None = None,
) -> dict[str, Any]:
    settings = load_settings()
    query = q.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Enter a search query.")
    selected = load_selection(settings)
    model_id = selected["text"]
    if not model_is_ready(settings, model_id):
        raise HTTPException(
            status_code=400,
            detail="The text embedding model is not ready. Download it from Home → Models.",
        )
    try:
        model_id, vectors = await encode_texts(
            settings, slot="text", texts=[query], is_query=True
        )
        vector = vectors[0]
    except EncoderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except EmbedUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    async with get_conn(settings) as conn:
        hits = await search_text_messages(
            conn,
            model_id=model_id,
            query=vector,
            limit=limit,
            peer_external_id=peer_external_id,
        )
        if not hits:
            return {
                "messages": [],
                "total": 0,
                "limit": limit,
                "offset": 0,
                "model_id": model_id,
                "q": query,
            }
        ids = [row["message_id"] for row in hits]
        rows = await conn.execute(
            f"""
            SELECT
                m.id, m.telegram_message_id, m.date, m.content,
                m.from_external_id, m.fwd_from, m.media,
                {_MESSAGE_PEER_COLUMNS}
            FROM messages m
            JOIN peers p ON p.external_id = m.peer_external_id
            WHERE m.id = ANY(%s)
            """,
            (ids,),
        )
        by_id = {str(row["id"]): dict(row) for row in await rows.fetchall()}
    messages = []
    for hit in hits:
        row = by_id.get(str(hit["message_id"]))
        if row is None:
            continue
        item = _public_message(row, data_dir=settings.data_dir)
        item["score"] = _score(hit)
        messages.append(item)
    return {
        "messages": messages,
        "total": len(messages),
        "limit": limit,
        "offset": 0,
        "model_id": model_id,
        "q": query,
    }


@router.get("/search/images")
async def search_images(
    q: str = Query(..., min_length=1),
    limit: int = Query(default=50, ge=1, le=200),
    peer_external_id: int | None = None,
) -> dict[str, Any]:
    settings = load_settings()
    query = q.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Enter a search query.")
    selected = load_selection(settings)
    model_id = selected["image"]
    if not model_is_ready(settings, model_id):
        raise HTTPException(
            status_code=400,
            detail="The vision model is not ready. Download it from Home → Models.",
        )
    if not vision_is_multimodal(model_id):
        raise HTTPException(
            status_code=400,
            detail=(
                "The selected vision model is image-only. "
                "Switch to CLIP or SigLIP for text-to-image search."
            ),
        )
    try:
        model_id, vectors = await encode_texts(
            settings, slot="image", texts=[query], is_query=True
        )
        vector = vectors[0]
    except EncoderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except EmbedUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    async with get_conn(settings) as conn:
        hits = await search_image_blobs(
            conn,
            model_id=model_id,
            query=vector,
            limit=limit,
            peer_external_id=peer_external_id,
        )
        if not hits:
            return {
                "images": [],
                "total": 0,
                "limit": limit,
                "offset": 0,
                "model_id": model_id,
                "q": query,
            }
        phashes = [str(row["phash"]) for row in hits]
        blob_rows = await conn.execute(
            """
            SELECT
                b.phash,
                b.canonical_path,
                b.refcount,
                COUNT(m.message_id) AS appearances,
                COUNT(DISTINCT m.peer_external_id) AS unique_peers,
                MAX(m.message_date) AS last_seen_at
            FROM image_blobs b
            LEFT JOIN image_blob_messages m ON m.phash = b.phash
            WHERE b.phash = ANY(%s)
            GROUP BY b.phash, b.canonical_path, b.refcount
            """,
            (phashes,),
        )
        by_phash = {str(row["phash"]): dict(row) for row in await blob_rows.fetchall()}
        ordered = [by_phash[phash] for phash in phashes if phash in by_phash]
        images = await _attach_image_peers(conn, ordered, data_dir=settings.data_dir)
        scores = {str(row["phash"]): _score(row) for row in hits}
        for item in images:
            item["score"] = scores.get(str(item["phash"]))
    return {
        "images": images,
        "total": len(images),
        "limit": limit,
        "offset": 0,
        "model_id": model_id,
        "q": query,
    }
