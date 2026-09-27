from telegram_snowball.jobs.download_model import run_download_model
from telegram_snowball.jobs.embed import run_embed
from telegram_snowball.jobs.fetch_dialogues import run_fetch_dialogues
from telegram_snowball.jobs.forward_snowball import run_forward_snowball

TASK_RUNNERS = {
    "fetch_dialogues": run_fetch_dialogues,
    "forward_snowball": run_forward_snowball,
    "download_model": run_download_model,
    "embed": run_embed,
}

__all__ = ["TASK_RUNNERS"]
