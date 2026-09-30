from __future__ import annotations

import asyncio
import logging
from contextlib import suppress

import uvicorn

from telegram_snowball.accesslog import quiet_health_access_logs
from telegram_snowball.config import load_settings
from telegram_snowball.embed.service import app
from telegram_snowball.worker.loop import run_worker


async def _run() -> None:
    settings = load_settings()
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    quiet_health_access_logs()
    config = uvicorn.Config(
        app,
        host=settings.snowball_embed_bind,
        port=settings.snowball_embed_port,
        log_level=settings.log_level.lower(),
    )
    server = uvicorn.Server(config)
    worker = asyncio.create_task(
        run_worker(settings, kind="embed", worker_id="embed-1"),
        name="embed-worker",
    )
    try:
        await server.serve()
    finally:
        worker.cancel()
        with suppress(asyncio.CancelledError):
            await worker


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
