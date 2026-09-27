from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

from telegram_snowball.config import Settings
from telegram_snowball.jobs.progress import raise_if_cancelled, update_job_progress
from telegram_snowball.models_catalog import (
    catalog_by_id,
    mark_model_ready,
    model_dir,
    save_selection,
)


def _download(repo_id: str, dest: str) -> None:
    from huggingface_hub import snapshot_download

    snapshot_download(
        repo_id=repo_id,
        local_dir=dest,
        allow_patterns=[
            "*.safetensors",
            "*.bin",
            "*.json",
            "*.txt",
            "*.model",
            "tokenizer*",
            "preprocessor*",
            "*.jinja",
        ],
    )


async def run_download_model(
    conn: Any,
    *,
    settings: Settings,
    job_id: UUID,
    params: dict[str, Any],
) -> None:
    model_id = str(params.get("model_id") or "")
    spec = catalog_by_id(model_id)
    if not spec.get("hf_id"):
        raise ValueError(f"{model_id} has nothing to download")
    dest = model_dir(settings, model_id)
    dest.mkdir(parents=True, exist_ok=True)
    await update_job_progress(
        conn,
        job_id,
        {
            "detail": f"Downloading {spec['label']}",
            "model_id": model_id,
            "slot": spec["slot"],
        },
    )
    await raise_if_cancelled(conn, job_id)
    await asyncio.to_thread(_download, str(spec["hf_id"]), str(dest))
    await raise_if_cancelled(conn, job_id)
    mark_model_ready(settings, model_id)
    save_selection(settings, {spec["slot"]: model_id})
    await update_job_progress(
        conn,
        job_id,
        {
            "detail": f"{spec['label']} is ready",
            "model_id": model_id,
            "slot": spec["slot"],
        },
    )
