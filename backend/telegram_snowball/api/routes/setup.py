from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, WebSocket
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError
from telethon.sessions import StringSession
from telethon.tl.types import User

from telegram_snowball.config import Settings, load_settings
from telegram_snowball.crypto import decrypt_text, encrypt_text, load_fernet
from telegram_snowball.db import get_conn
from telegram_snowball.telegram.client import session_string_from_client
from telegram_snowball.telegram.profile_photos import harvest_profile_photo

lg = logging.getLogger(__name__)
router = APIRouter(prefix="/setup")


class CredentialsIn(BaseModel):
    api_id: int = Field(..., gt=0)
    api_hash: str = Field(..., min_length=8)


async def _persist_credentials(
    conn, settings: Settings, api_id: int, api_hash: str
) -> None:
    fernet = load_fernet(settings)
    payload = {
        "api_id_enc": encrypt_text(fernet, str(api_id)),
        "api_hash_enc": encrypt_text(fernet, api_hash.strip()),
    }
    await conn.execute(
        """
        INSERT INTO app_settings (key, value, updated_at)
        VALUES ('telegram_credentials', %s, now())
        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()
        """,
        (Jsonb(payload),),
    )


async def seed_credentials_from_env(conn, settings: Settings) -> bool:
    pair = settings.env_telegram_api()
    if not pair:
        return False
    row = await conn.execute("SELECT 1 FROM app_settings WHERE key = 'telegram_credentials'")
    if await row.fetchone():
        return False
    await _persist_credentials(conn, settings, pair[0], pair[1])
    await conn.commit()
    return True


async def _load_plain_credentials() -> tuple[int, str]:
    settings = load_settings()
    async with get_conn(settings) as conn:
        row = await conn.execute(
            "SELECT value FROM app_settings WHERE key = 'telegram_credentials'"
        )
        data = await row.fetchone()
        if data:
            fernet = load_fernet(settings)
            payload = data["value"]
            return int(decrypt_text(fernet, payload["api_id_enc"])), decrypt_text(
                fernet, payload["api_hash_enc"]
            )
        pair = settings.env_telegram_api()
        if pair:
            await _persist_credentials(conn, settings, pair[0], pair[1])
            await conn.commit()
            return pair
    raise HTTPException(status_code=400, detail="Save API credentials first.")


@router.put("/credentials")
async def save_credentials(body: CredentialsIn) -> dict[str, bool]:
    settings = load_settings()
    async with get_conn(settings) as conn:
        await _persist_credentials(conn, settings, body.api_id, body.api_hash)
        await conn.commit()
    return {"ok": True}


async def _sign_in(client: TelegramClient, websocket: WebSocket, phone: str) -> User:
    await client.send_code_request(phone)
    await websocket.send_json({"message": "Enter code"})
    data = await websocket.receive_json()
    code = str(data.get("code") or "").strip()
    if not code:
        raise ValueError("Missing login code")
    try:
        result = await client.sign_in(phone, code)
        if isinstance(result, User):
            return result
    except SessionPasswordNeededError:
        await websocket.send_json({"message": "2FA is enabled. Enter 2FA password"})
        data = await websocket.receive_json()
        password = str(data.get("password") or "")
        if not password:
            raise ValueError("Missing 2FA password")
        result = await client.sign_in(password=password)
        if isinstance(result, User):
            return result
    me = await client.get_me()
    if isinstance(me, User):
        return me
    raise ValueError("Could not complete Telegram sign-in")


@router.websocket("/session")
async def setup_session(websocket: WebSocket) -> None:
    await websocket.accept()
    settings = load_settings()
    client: TelegramClient | None = None
    try:
        async with get_conn(settings) as conn:
            existing = await conn.execute("SELECT id FROM telegram_sessions LIMIT 1")
            if await existing.fetchone():
                await websocket.send_json(
                    {"error": "A Telegram session already exists. v1 allows only one session."}
                )
                await websocket.close(code=1011)
                return

        api_id, api_hash = await _load_plain_credentials()
        data = await websocket.receive_json()
        phone = str(data.get("phone_number") or "").strip()
        if not phone:
            await websocket.send_json({"error": "Missing phone_number"})
            await websocket.close(code=1011)
            return

        client = TelegramClient(StringSession(), api_id, api_hash)
        await client.connect()
        user = await _sign_in(client, websocket, phone)
        session_string = session_string_from_client(client)
        fernet = load_fernet(settings)
        session_enc = encrypt_text(fernet, session_string)
        photo_path = None
        photo_media_kind = None
        try:
            harvested = await harvest_profile_photo(
                client,
                settings=settings,
                entity=user,
                peer_type="user",
                external_id=int(user.id),
            )
            if harvested:
                photo_path = harvested.rel_path
                photo_media_kind = harvested.media_kind
        except Exception:
            lg.warning("could not harvest account profile photo during setup", exc_info=True)

        async with get_conn(settings) as conn:
            account = await conn.execute(
                """
                INSERT INTO telegram_accounts (
                    telegram_user_id, phone, username, first_name, last_name,
                    photo_path, photo_media_kind, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, now())
                ON CONFLICT (telegram_user_id) DO UPDATE SET
                    phone = EXCLUDED.phone,
                    username = EXCLUDED.username,
                    first_name = EXCLUDED.first_name,
                    last_name = EXCLUDED.last_name,
                    photo_path = COALESCE(EXCLUDED.photo_path, telegram_accounts.photo_path),
                    photo_media_kind = COALESCE(EXCLUDED.photo_media_kind, telegram_accounts.photo_media_kind),
                    updated_at = now()
                RETURNING id
                """,
                (
                    int(user.id),
                    user.phone or phone,
                    user.username,
                    user.first_name,
                    user.last_name,
                    photo_path,
                    photo_media_kind,
                ),
            )
            account_row = await account.fetchone()
            assert account_row is not None
            try:
                await conn.execute(
                    """
                    INSERT INTO telegram_sessions (account_id, session_enc, auth_state)
                    VALUES (%s, %s, 'healthy')
                    """,
                    (account_row["id"], session_enc),
                )
            except Exception:
                await conn.rollback()
                await websocket.send_json(
                    {"error": "A Telegram session already exists. v1 allows only one session."}
                )
                await websocket.close(code=1011)
                return
            await conn.commit()

        await websocket.send_json({"message": "ok", "user_id": int(user.id)})
        await websocket.close(code=1000)
    except Exception as exc:
        lg.exception("session setup failed")
        try:
            await websocket.send_json({"error": str(exc)})
            await websocket.close(code=1011)
        except Exception:
            pass
    finally:
        if client is not None and client.is_connected():
            result = client.disconnect()
            if result is not None:
                await result


@router.delete("/session")
async def delete_session() -> dict[str, bool]:
    """Drop the v1 Telegram session so Home can change or remove the account."""
    settings = load_settings()
    async with get_conn(settings) as conn:
        existing = await conn.execute("SELECT id FROM telegram_sessions LIMIT 1")
        if await existing.fetchone() is None:
            raise HTTPException(status_code=404, detail="No Telegram session to remove.")
        await conn.execute(
            """
            UPDATE jobs
            SET status = 'cancelled',
                finished_at = COALESCE(finished_at, now()),
                heartbeat_at = now()
            WHERE status IN ('queued', 'running')
            """
        )
        await conn.execute(
            "UPDATE peers SET is_scraping = false, scrape_detail = NULL WHERE is_scraping = true"
        )
        await conn.execute("DELETE FROM telegram_sessions")
        await conn.execute("DELETE FROM telegram_accounts")
        await conn.commit()
    return {"ok": True}
