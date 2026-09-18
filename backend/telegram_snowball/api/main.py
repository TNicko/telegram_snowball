from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from telegram_snowball.config import load_settings
from telegram_snowball.db import apply_schema, connect_with_retry
from telegram_snowball.api.routes import dialogues, jobs, models, setup, status


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings = load_settings()
    conn = await connect_with_retry(settings.postgres_dsn)
    try:
        await apply_schema(conn)
    finally:
        await conn.close()
    yield


app = FastAPI(title="Telegram Snowball", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:8080",
        "http://localhost:8080",
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:80",
        "http://localhost:80",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(status.router, prefix="/api")
app.include_router(setup.router, prefix="/api")
app.include_router(models.router, prefix="/api")
app.include_router(jobs.router, prefix="/api")
app.include_router(dialogues.router, prefix="/api")


def run() -> None:
    import uvicorn

    settings = load_settings()
    uvicorn.run(
        "telegram_snowball.api.main:app",
        host=settings.snowball_bind,
        port=settings.snowball_api_port,
        reload=True,
    )
