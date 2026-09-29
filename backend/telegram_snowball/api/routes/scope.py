"""Home Scope inputs: text + image files encoded in the vision sidecar."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from telegram_snowball.config import load_settings
from telegram_snowball.db import get_conn
from telegram_snowball.embed.client import EmbedUnavailable, encode_images, encode_texts
from telegram_snowball.embed.runtime import EncoderError, vision_is_multimodal
from telegram_snowball.models_catalog import load_selection, model_is_ready
from telegram_snowball.scope.store import delete_input, get_input, insert_input, list_inputs, load_params

router = APIRouter()

_MAX_TEXT = 2000
_MAX_FILE = 12 * 1024 * 1024
_IMAGE_TYPES = {
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/webp",
    "image/gif",
    "image/bmp",
}


class ScopeTextIn(BaseModel):
    text: str = Field(..., min_length=1, max_length=_MAX_TEXT)


def _scope_dir(data_dir: Path) -> Path:
    dest = data_dir / "scope"
    dest.mkdir(parents=True, exist_ok=True)
    return dest


async def _require_vision(*, for_text: bool) -> str:
    settings = load_settings()
    selected = load_selection(settings)
    model_id = selected["image"]
    if not model_is_ready(settings, model_id):
        raise HTTPException(
            status_code=400,
            detail="The vision model is not ready. Download it from Home → Models.",
        )
    if for_text and not vision_is_multimodal(model_id):
        raise HTTPException(
            status_code=400,
            detail=(
                "The selected vision model is image-only. "
                "Switch to CLIP or SigLIP to add text Scope prompts."
            ),
        )
    return model_id


async def _scope_payload(conn: Any) -> dict[str, Any]:
    params = await load_params(conn)
    inputs = await list_inputs(conn)
    row = await conn.execute(
        "SELECT last_rerank_at, updated_at FROM scope_state WHERE id = 1"
    )
    extra = await row.fetchone()
    last_rerank = extra["last_rerank_at"] if extra else None
    updated = extra["updated_at"] if extra else None
    needs_rescore = bool(inputs) and (last_rerank is None or (updated is not None and updated > last_rerank))
    return {
        "inputs": inputs,
        "tau": params.tau,
        "gamma": params.gamma,
        "alpha": params.alpha,
        "delta": params.delta,
        "lambda_fwd": params.lambda_fwd,
        "version": params.version,
        "last_rerank_at": last_rerank,
        "needs_rescore": needs_rescore,
    }


@router.get("/scope")
async def get_scope() -> dict[str, Any]:
    settings = load_settings()
    async with get_conn(settings) as conn:
        return await _scope_payload(conn)


@router.post("/scope/inputs/text")
async def add_scope_text(body: ScopeTextIn) -> dict[str, Any]:
    text = body.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Enter a Scope prompt.")
    await _require_vision(for_text=True)
    settings = load_settings()
    try:
        model_id, vectors = await encode_texts(
            settings, slot="image", texts=[text], is_query=True
        )
    except EncoderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except EmbedUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    vector = vectors[0]
    async with get_conn(settings) as conn:
        item = await insert_input(
            conn,
            kind="text",
            body=text,
            filename=None,
            content_type="text/plain",
            values=vector,
            model_id=model_id,
            dim=int(len(vector)),
        )
        await conn.commit()
        payload = await _scope_payload(conn)
    payload["added"] = item
    return payload


@router.post("/scope/inputs/file")
async def add_scope_file(file: UploadFile = File(...)) -> dict[str, Any]:
    await _require_vision(for_text=False)
    content_type = (file.content_type or "").split(";")[0].strip().lower()
    name = (file.filename or "image").strip() or "image"
    if content_type and content_type not in _IMAGE_TYPES and not content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Scope files must be images.")
    payload_bytes = await file.read()
    if not payload_bytes:
        raise HTTPException(status_code=400, detail="That file was empty.")
    if len(payload_bytes) > _MAX_FILE:
        raise HTTPException(status_code=400, detail="Image is larger than 12 MB.")
    settings = load_settings()
    try:
        model_id, vectors = await encode_images(settings, payloads=[payload_bytes])
    except EncoderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except EmbedUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    vector = vectors[0]
    async with get_conn(settings) as conn:
        item = await insert_input(
            conn,
            kind="file",
            body="",
            filename=name,
            content_type=content_type or "image/*",
            values=vector,
            model_id=model_id,
            dim=int(len(vector)),
        )
        dest = _scope_dir(settings.data_dir) / str(item["id"])
        dest.write_bytes(payload_bytes)
        await conn.execute(
            "UPDATE scope_inputs SET body = %s WHERE id = %s",
            (str(dest.relative_to(settings.data_dir)), item["id"]),
        )
        await conn.commit()
        payload = await _scope_payload(conn)
    payload["added"] = item
    return payload


@router.delete("/scope/inputs/{input_id}")
async def remove_scope_input(input_id: UUID) -> dict[str, Any]:
    settings = load_settings()
    async with get_conn(settings) as conn:
        existing = await get_input(conn, input_id)
        if existing is None:
            raise HTTPException(status_code=404, detail="Scope input not found")
        await delete_input(conn, input_id)
        await conn.commit()
        if existing.get("kind") == "file":
            rel = str(existing.get("body") or "")
            if rel:
                path = settings.data_dir / rel
                if path.is_file() and path.resolve().is_relative_to(settings.data_dir.resolve()):
                    path.unlink(missing_ok=True)
        return await _scope_payload(conn)


@router.get("/scope/inputs/{input_id}/file", response_model=None)
async def scope_input_file(input_id: UUID) -> FileResponse:
    settings = load_settings()
    async with get_conn(settings) as conn:
        existing = await get_input(conn, input_id)
    if existing is None or existing.get("kind") != "file":
        raise HTTPException(status_code=404, detail="Scope image not found")
    rel = str(existing.get("body") or "")
    path = (settings.data_dir / rel).resolve()
    if not path.is_file() or not path.is_relative_to(settings.data_dir.resolve()):
        raise HTTPException(status_code=404, detail="Scope image not found")
    media = str(existing.get("content_type") or "image/jpeg")
    filename = str(existing.get("filename") or path.name)
    return FileResponse(path, media_type=media, filename=filename)
