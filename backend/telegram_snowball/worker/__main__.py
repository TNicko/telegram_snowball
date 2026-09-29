from __future__ import annotations

import asyncio

from telegram_snowball.config import load_settings
from telegram_snowball.worker.loop import run_worker


def main() -> None:
    settings = load_settings()
    kind = (settings.snowball_worker_kind or "scrape").strip().lower()
    asyncio.run(run_worker(settings, kind=kind, worker_id=f"{kind}-1"))


if __name__ == "__main__":
    main()
