"""HTTP client for the embed sidecar (encode + peer backfill)."""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

import httpx
import numpy as np

from telegram_snowball.config import Settings
from telegram_snowball.embed.runtime import EncoderError
from telegram_snowball.jobs.progress import JobCancelled

lg = logging.getLogger(__name__)


class EmbedUnavailable(RuntimeError):
    def __init__(self, message: str | None = None) -> None:
        super().__init__(
            message
            or "The embedding sidecar is not running. Start the embed service, then retry."
        )


def _url(settings: Settings, path: str) -> str:
    return f"{settings.snowball_embed_url.rstrip('/')}{path}"


def _detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        text = response.text.strip()
        return text or f"embed sidecar HTTP {response.status_code}"
    detail = payload.get("detail") if isinstance(payload, dict) else None
    if isinstance(detail, str) and detail.strip():
        return detail
    if isinstance(detail, list) and detail:
        return str(detail[0])
    return f"embed sidecar HTTP {response.status_code}"


async def _request(
    settings: Settings,
    method: str,
    path: str,
    *,
    json: dict[str, Any] | None = None,
    timeout: httpx.Timeout,
) -> httpx.Response:
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.request(method, _url(settings, path), json=json)
    except httpx.RequestError as exc:
        raise EmbedUnavailable() from exc
    if response.status_code == 400:
        raise EncoderError(_detail(response))
    if response.status_code == 409:
        raise JobCancelled()
    if response.status_code in {502, 503, 504}:
        raise EmbedUnavailable(_detail(response))
    if response.status_code >= 400:
        raise EncoderError(_detail(response))
    return response


def _vectors_from_response(data: dict[str, Any], expected: int) -> tuple[str, list[np.ndarray]]:
    model_id = str(data.get("model_id") or "")
    raw = data.get("vectors") or []
    vectors = [np.asarray(item, dtype=np.float32) for item in raw]
    if not model_id or len(vectors) != expected:
        raise EncoderError("Embedding sidecar returned an incomplete encode response.")
    return model_id, vectors


async def encode_texts(
    settings: Settings,
    *,
    slot: str,
    texts: list[str],
    is_query: bool = False,
) -> tuple[str, list[np.ndarray]]:
    response = await _request(
        settings,
        "POST",
        "/encode/text",
        json={"slot": slot, "texts": texts, "is_query": is_query},
        timeout=httpx.Timeout(180.0, connect=5.0),
    )
    return _vectors_from_response(response.json(), len(texts))


async def encode_images(
    settings: Settings,
    *,
    payloads: list[bytes],
) -> tuple[str, list[np.ndarray]]:
    import base64

    if not payloads:
        raise EncoderError("No images to encode")
    encoded = [base64.b64encode(item).decode("ascii") for item in payloads]
    response = await _request(
        settings,
        "POST",
        "/encode/image",
        json={"images_b64": encoded},
        timeout=httpx.Timeout(180.0, connect=5.0),
    )
    return _vectors_from_response(response.json(), len(payloads))


async def embed_peer(
    settings: Settings,
    *,
    peer_external_id: int,
    text: bool,
    images: bool,
    job_id: UUID | None = None,
) -> None:
    await _request(
        settings,
        "POST",
        "/embed/peer",
        json={
            "peer_external_id": peer_external_id,
            "text": text,
            "images": images,
            "job_id": str(job_id) if job_id is not None else None,
        },
        timeout=httpx.Timeout(3600.0, connect=5.0),
    )


async def drop_cached_remote(settings: Settings, model_id: str | None = None) -> None:
    try:
        await _request(
            settings,
            "POST",
            "/cache/drop",
            json={"model_id": model_id},
            timeout=httpx.Timeout(10.0, connect=3.0),
        )
    except (EmbedUnavailable, EncoderError, JobCancelled):
        lg.warning("embed sidecar unreachable; skipped encoder cache drop")
