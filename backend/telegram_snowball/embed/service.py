"""HTTP encode API for the embed sidecar."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, Literal
from uuid import UUID

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from telegram_snowball.accesslog import quiet_health_access_logs
from telegram_snowball.config import load_settings
from telegram_snowball.db import get_conn
from telegram_snowball.embed.runtime import EncoderError, drop_cached, load_encoder
from telegram_snowball.embed.worklock import inference_lock
from telegram_snowball.jobs.progress import JobCancelled


@asynccontextmanager
async def lifespan(_app: FastAPI):
    quiet_health_access_logs()
    yield


app = FastAPI(title="Telegram Snowball embed", lifespan=lifespan)


class EncodeTextIn(BaseModel):
    slot: Literal["text", "image"]
    texts: list[str] = Field(..., min_length=1)
    is_query: bool = False


class EncodeImageIn(BaseModel):
    images_b64: list[str] = Field(..., min_length=1)


class EmbedPeerIn(BaseModel):
    peer_external_id: int
    text: bool = True
    images: bool = True
    job_id: UUID | None = None


class DropCacheIn(BaseModel):
    model_id: str | None = None


def _vector_lists(values: list[Any]) -> list[list[float]]:
    out: list[list[float]] = []
    for item in values:
        out.append([float(x) for x in item.reshape(-1)])
    return out


@app.get("/health")
async def health() -> dict[str, bool]:
    return {"ok": True}


@app.post("/encode/text")
async def encode_text(body: EncodeTextIn) -> dict[str, Any]:
    settings = load_settings()
    texts = [str(item) for item in body.texts]
    async with inference_lock():
        try:
            encoder = load_encoder(settings, body.slot)
            vectors = encoder.encode_texts(texts, is_query=body.is_query)
        except EncoderError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"model_id": encoder.model_id, "vectors": _vector_lists(vectors)}


@app.post("/encode/image")
async def encode_image(body: EncodeImageIn) -> dict[str, Any]:
    import base64

    payloads: list[bytes] = []
    for item in body.images_b64:
        try:
            payloads.append(base64.b64decode(item, validate=False))
        except (ValueError, TypeError) as exc:
            raise HTTPException(status_code=400, detail="Invalid image payload") from exc
        if not payloads[-1]:
            raise HTTPException(status_code=400, detail="Empty image payload")
    settings = load_settings()
    async with inference_lock():
        try:
            encoder = load_encoder(settings, "image")
            vectors = encoder.encode_images(payloads)
        except EncoderError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"model_id": encoder.model_id, "vectors": _vector_lists(vectors)}


@app.post("/embed/peer")
async def embed_peer(body: EmbedPeerIn) -> dict[str, int]:
    from telegram_snowball.jobs.embed import embed_peer_pending

    settings = load_settings()
    async with inference_lock():
        try:
            async with get_conn(settings) as conn:
                await embed_peer_pending(
                    conn,
                    settings,
                    job_id=body.job_id,
                    peer_external_id=body.peer_external_id,
                    text=body.text,
                    images=body.images,
                )
        except EncoderError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except JobCancelled:
            raise HTTPException(status_code=409, detail="Job cancelled") from None
    return {"ok": 1}


@app.post("/cache/drop")
async def cache_drop(body: DropCacheIn) -> dict[str, bool]:
    drop_cached(body.model_id)
    return {"ok": True}
