from __future__ import annotations

from fastapi import APIRouter

from telegram_snowball.config import load_settings
from telegram_snowball.models_health import models_health

router = APIRouter(prefix="/models")


@router.get("/health")
async def get_models_health() -> dict:
    return models_health(load_settings())
