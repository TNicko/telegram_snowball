"""Download a catalog model into data/models/<id>/ and mark it ready."""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any
from uuid import UUID

from telegram_snowball.bytesfmt import format_bytes
from telegram_snowball.config import Settings
from telegram_snowball.jobs.progress import (
    JobCancelled,
    job_is_cancelled,
    raise_if_cancelled,
    update_job_progress,
)
from telegram_snowball.models_catalog import (
    catalog_by_id,
    mark_model_ready,
    model_dir,
    save_selection,
)

lg = logging.getLogger(__name__)

ALLOW_PATTERNS = [
    "*.safetensors",
    "*.bin",
    "*.json",
    "*.txt",
    "*.model",
    "tokenizer*",
    "preprocessor*",
    "*.jinja",
]


class _DownloadBytes:
    def __init__(self, expected: int | None) -> None:
        self.lock = threading.Lock()
        self.done = 0
        self.total = int(expected or 0)

    def note(self, done: int, total: int | None = None) -> None:
        with self.lock:
            self.done = max(self.done, int(done or 0))
            if total:
                self.total = max(self.total, int(total))

    def snapshot(self) -> tuple[int, int]:
        with self.lock:
            return self.done, self.total


def download_percent(done: int, total: int) -> int | None:
    if total <= 0:
        return None
    if done <= 0:
        return 0
    return min(99, int(done * 100 / total))


def fallback_expected_bytes(download_gb: Any) -> int | None:
    try:
        value = float(download_gb)
    except (TypeError, ValueError):
        return None
    if value <= 0:
        return None
    return int(value * 1_000_000_000)


def expected_repo_bytes(repo_id: str) -> int | None:
    try:
        from huggingface_hub import HfApi
        from huggingface_hub.utils import filter_repo_objects
    except ImportError:
        return None
    try:
        sizes: dict[str, int] = {}
        for item in HfApi().list_repo_tree(repo_id, recursive=True):
            path = getattr(item, "path", None)
            size = getattr(item, "size", None)
            if path and size:
                sizes[str(path)] = int(size)
        kept = list(filter_repo_objects(sizes, allow_patterns=ALLOW_PATTERNS))
        total = sum(sizes[path] for path in kept)
    except Exception:
        lg.exception("could not list file sizes for %s", repo_id)
        return None
    return total or None


def _progress_tqdm(state: _DownloadBytes) -> type:
    from huggingface_hub.utils import tqdm as hf_tqdm

    class ReportTqdm(hf_tqdm):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            kwargs["disable"] = True
            super().__init__(*args, **kwargs)
            self._report()

        def update(self, n: float | int = 1) -> Any:
            result = super().update(n)
            self._report()
            return result

        def refresh(self, *args: Any, **kwargs: Any) -> Any:
            result = super().refresh(*args, **kwargs)
            self._report()
            return result

        def _report(self) -> None:
            if str(getattr(self, "unit", "") or "") != "B":
                return
            desc = str(getattr(self, "desc", "") or "")
            name = str(getattr(self, "name", "") or "")
            if desc.startswith("Downloading bytes") or "transfer" in name:
                return
            state.note(int(self.n or 0), int(self.total or 0) or None)

    return ReportTqdm


def _download(repo_id: str, dest: str, state: _DownloadBytes) -> None:
    from huggingface_hub import snapshot_download

    listed = expected_repo_bytes(repo_id)
    if listed:
        state.note(0, listed)
    snapshot_download(
        repo_id=repo_id,
        local_dir=dest,
        allow_patterns=ALLOW_PATTERNS,
        tqdm_class=_progress_tqdm(state),
    )


def progress_fields(
    *,
    label: str,
    model_id: str,
    slot: str,
    done: int,
    total: int,
    finished: bool = False,
) -> dict[str, Any]:
    percent = 100 if finished else download_percent(done, total)
    if finished:
        detail = f"{label} is ready"
    elif percent is None:
        detail = f"Downloading {label}"
    else:
        detail = f"Downloading weights · {percent}%"
        if done > 0:
            sizes = format_bytes(done)
            total_text = format_bytes(total)
            if sizes and total_text:
                detail = f"{detail} · {sizes} / {total_text}"
    out: dict[str, Any] = {
        "detail": detail,
        "model_id": model_id,
        "model_label": label,
        "slot": slot,
        "downloaded_bytes": int(done),
        "total_bytes": int(total) if total > 0 else None,
        "percent": percent,
        "phase": "ready" if finished else "download",
    }
    return out


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
    label = str(spec["label"])
    slot = str(spec["slot"])
    state = _DownloadBytes(fallback_expected_bytes(spec.get("download_gb")))
    await update_job_progress(
        conn,
        job_id,
        progress_fields(label=label, model_id=model_id, slot=slot, done=0, total=state.total),
    )
    await raise_if_cancelled(conn, job_id)
    download_task = asyncio.create_task(
        asyncio.to_thread(_download, str(spec["hf_id"]), str(dest), state)
    )
    cancelled = False
    try:
        while not download_task.done():
            done, total = state.snapshot()
            await update_job_progress(
                conn,
                job_id,
                progress_fields(
                    label=label, model_id=model_id, slot=slot, done=done, total=total
                ),
            )
            if await job_is_cancelled(conn, job_id):
                cancelled = True
            try:
                await asyncio.wait_for(asyncio.shield(download_task), timeout=0.4)
            except TimeoutError:
                continue
        await download_task
    except Exception:
        download_task.cancel()
        raise
    if cancelled:
        raise JobCancelled()
    await raise_if_cancelled(conn, job_id)
    mark_model_ready(settings, model_id)
    save_selection(settings, {spec["slot"]: model_id})
    done, total = state.snapshot()
    await update_job_progress(
        conn,
        job_id,
        progress_fields(
            label=label,
            model_id=model_id,
            slot=slot,
            done=max(done, total),
            total=total,
            finished=True,
        ),
    )
