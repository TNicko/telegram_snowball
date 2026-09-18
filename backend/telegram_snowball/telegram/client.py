from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from telethon import TelegramClient
from telethon.sessions import StringSession

from telegram_snowball.config import Settings
from telegram_snowball.crypto import decrypt_text, load_fernet
from telegram_snowball.db import get_conn


async def load_credentials(settings: Settings) -> tuple[int, str]:
    async with get_conn(settings) as conn:
        row = await conn.execute(
            "SELECT value FROM app_settings WHERE key = %s",
            ("telegram_credentials",),
        )
        data = await row.fetchone()
    if not data:
        raise RuntimeError("Telegram API credentials are not set. Finish setup first.")
    payload = data["value"]
    fernet = load_fernet(settings)
    api_id = int(decrypt_text(fernet, payload["api_id_enc"]))
    api_hash = decrypt_text(fernet, payload["api_hash_enc"])
    return api_id, api_hash


async def load_session_string(settings: Settings) -> str:
    async with get_conn(settings) as conn:
        row = await conn.execute("SELECT session_enc FROM telegram_sessions LIMIT 1")
        data = await row.fetchone()
    if not data:
        raise RuntimeError("No Telegram session. Finish account setup first.")
    return decrypt_text(load_fernet(settings), data["session_enc"])


@asynccontextmanager
async def telegram_client(settings: Settings) -> AsyncIterator[TelegramClient]:
    api_id, api_hash = await load_credentials(settings)
    session = await load_session_string(settings)
    client = TelegramClient(StringSession(session), api_id, api_hash)
    await client.connect()
    try:
        if not await client.is_user_authorized():
            raise RuntimeError("Telegram session is no longer authorized.")
        yield client
    finally:
        if client.is_connected():
            result = client.disconnect()
            if result is not None:
                await result


def session_string_from_client(client: TelegramClient) -> str:
    session = client.session
    if not isinstance(session, StringSession):
        raise TypeError("Expected StringSession")
    saved: Any = session.save()
    return str(saved)
