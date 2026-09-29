from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from psycopg.types.json import Jsonb

from telegram_snowball.config import load_settings
from telegram_snowball.db import get_conn
from telegram_snowball.jobs.lanes import live_conflict_detail, live_job_in_lane
from telegram_snowball.jsonutil import json_safe
from telegram_snowball.models_catalog import catalog_by_id, load_selection, model_is_ready, save_selection
from telegram_snowball.models_health import models_catalog_payload

router = APIRouter(prefix="/models")


class SelectModelsIn(BaseModel):
    image: str | None = None
    text: str | None = None


class DownloadModelIn(BaseModel):
    model_id: str = Field(..., min_length=1)


async def _attach_download(payload: dict[str, Any]) -> dict[str, Any]:
    settings = load_settings()
    async with get_conn(settings) as conn:
        row = await conn.execute(
            """
            SELECT id, task_type, status, params, progress, error, created_at
            FROM jobs
            WHERE task_type = 'download_model' AND status IN ('queued', 'running')
            ORDER BY created_at DESC
            LIMIT 1
            """
        )
        job = await row.fetchone()
    payload["download"] = dict(job) if job else None
    return payload


@router.get("/")
@router.get("")
@router.get("/health")
async def get_models() -> dict[str, Any]:
    return await _attach_download(models_catalog_payload(load_settings()))


@router.put("/selection")
async def select_models(body: SelectModelsIn) -> dict[str, Any]:
    settings = load_settings()
    patch = {slot: value for slot, value in body.model_dump().items() if value}
    if not patch:
        raise HTTPException(status_code=400, detail="Choose at least one model slot.")
    previous = load_selection(settings)
    try:
        selected = save_selection(settings, patch)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if previous["text"] != selected["text"] or previous["image"] != selected["image"]:
        from telegram_snowball.embed.client import drop_cached_remote
        from telegram_snowball.embed.store import reset_image_embeddings, reset_text_embeddings

        async with get_conn(settings) as conn:
            if previous["text"] != selected["text"]:
                await reset_text_embeddings(conn)
                await drop_cached_remote(settings, previous["text"])
            if previous["image"] != selected["image"]:
                await reset_image_embeddings(conn)
                await drop_cached_remote(settings, previous["image"])
            await conn.commit()
    return await _attach_download(models_catalog_payload(settings))


@router.post("/download")
async def download_model(body: DownloadModelIn) -> dict[str, Any]:
    settings = load_settings()
    try:
        spec = catalog_by_id(body.model_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Unknown model") from exc
    if not spec.get("hf_id"):
        save_selection(settings, {spec["slot"]: spec["id"]})
        return await _attach_download(
            {"queued": False, "ready": True, **models_catalog_payload(settings)}
        )
    if model_is_ready(settings, spec["id"]):
        save_selection(settings, {spec["slot"]: spec["id"]})
        return await _attach_download(
            {"queued": False, "ready": True, **models_catalog_payload(settings)}
        )

    async with get_conn(settings) as conn:
        if await live_job_in_lane(conn, "embed"):
            raise HTTPException(
                status_code=409,
                detail=f"{live_conflict_detail('embed')} Wait for it to finish, then download the model.",
            )
        inserted = await conn.execute(
            """
            INSERT INTO jobs (task_type, status, params)
            VALUES ('download_model', 'queued', %s)
            RETURNING id, task_type, status, params, progress, created_at
            """,
            (Jsonb(json_safe({"model_id": spec["id"], "slot": spec["slot"]})),),
        )
        job = await inserted.fetchone()
        await conn.commit()
    save_selection(settings, {spec["slot"]: spec["id"]})
    payload = models_catalog_payload(settings)
    payload["queued"] = True
    payload["ready"] = False
    payload["job"] = dict(job) if job else None
    return await _attach_download(payload)
