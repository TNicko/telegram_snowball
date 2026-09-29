from __future__ import annotations

from collections.abc import Awaitable, Callable

from telegram_snowball.jobs.fetch_dialogues import run_fetch_dialogues
from telegram_snowball.jobs.forward_snowball import run_forward_snowball

JobRunner = Callable[..., Awaitable[None]]

SCRAPE_RUNNERS: dict[str, JobRunner] = {
    "fetch_dialogues": run_fetch_dialogues,
    "forward_snowball": run_forward_snowball,
}


def _embed_runners() -> dict[str, JobRunner]:
    from telegram_snowball.jobs.download_model import run_download_model
    from telegram_snowball.jobs.embed import run_embed
    from telegram_snowball.jobs.scope_rerank import run_scope_rerank

    return {
        "download_model": run_download_model,
        "embed": run_embed,
        "scope_rerank": run_scope_rerank,
    }


def runners_for(kind: str) -> dict[str, JobRunner]:
    if kind == "embed":
        return _embed_runners()
    return SCRAPE_RUNNERS


TASK_RUNNERS: dict[str, JobRunner] = {**SCRAPE_RUNNERS}

__all__ = ["TASK_RUNNERS", "runners_for"]
