from telegram_snowball.jobs.fetch_dialogues import run_fetch_dialogues
from telegram_snowball.jobs.forward_snowball import run_forward_snowball

TASK_RUNNERS = {
    "fetch_dialogues": run_fetch_dialogues,
    "forward_snowball": run_forward_snowball,
}

__all__ = ["TASK_RUNNERS"]
