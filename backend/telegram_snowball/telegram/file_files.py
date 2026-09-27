"""On-demand Telegram file download for leftover documents (not image/video)."""

from __future__ import annotations

import logging
import re
import uuid
from pathlib import Path
from typing import Any

from telethon import TelegramClient
from telethon.errors import FloodWaitError
from telethon.tl.types import Message

from telegram_snowball.catalog import stored_kind_is
from telegram_snowball.config import Settings
from telegram_snowball.telegram.image_files import resolve_under_data_dir
from telegram_snowball.telegram.resolve import entity_for_peer

lg = logging.getLogger(__name__)

_DOC_ID_RE = re.compile(r"^[0-9]+$")
_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


class FileUnavailable(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


def parse_file_id(file_id: str) -> tuple[str, str]:
    raw = (file_id or "").strip()
    if raw.lower().startswith("msg:"):
        raw = raw[4:]
    if _DOC_ID_RE.fullmatch(raw):
        return "document", raw
    if _UUID_RE.fullmatch(raw):
        return "message", raw.lower()
    raise FileUnavailable(404, "File not found")


def file_catalog_url(file_id: str) -> str:
    kind, ident = parse_file_id(file_id)
    if kind == "message":
        return f"/api/files/msg/{ident}/file"
    return f"/api/files/{ident}/file"


def safe_filename(name: str | None, *, mime: str | None = None) -> str:
    raw = (name or "").replace("\\", "/").rsplit("/", 1)[-1].strip()
    cleaned = "".join(ch for ch in raw if ch.isprintable() and ch not in '<>:"|?*')
    cleaned = cleaned.strip(" .")
    if cleaned:
        return cleaned[:180]
    mime = (mime or "").lower()
    if "pdf" in mime:
        return "file.pdf"
    if "zip" in mime:
        return "file.zip"
    if "word" in mime or mime.endswith("msword"):
        return "file.docx"
    if "spreadsheet" in mime or "excel" in mime:
        return "file.xlsx"
    return "file.bin"


def content_type_for_file(mime: str | None, path: Path | None = None) -> str:
    if mime and "/" in mime and not mime.startswith("application/octet-stream"):
        return mime
    suffix = path.suffix.lower() if path is not None else ""
    return {
        ".pdf": "application/pdf",
        ".zip": "application/zip",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".txt": "text/plain",
    }.get(suffix, "application/octet-stream")


async def lookup_file_sources(
    conn: Any,
    *,
    kind: str,
    ident: str,
) -> list[dict[str, Any]]:
    if kind == "document":
        rows = await conn.execute(
            f"""
            SELECT id, peer_external_id, telegram_message_id, media
            FROM messages
            WHERE {stored_kind_is("document")}
              AND media->>'document_id' = %s
            ORDER BY date DESC NULLS LAST
            LIMIT 16
            """,
            (ident,),
        )
    else:
        rows = await conn.execute(
            f"""
            SELECT id, peer_external_id, telegram_message_id, media
            FROM messages
            WHERE id = %s::uuid
              AND {stored_kind_is("document")}
            """,
            (ident,),
        )
    return [dict(row) for row in await rows.fetchall()]


def persisted_file_path(settings: Settings, media: dict[str, Any] | None) -> Path | None:
    if not isinstance(media, dict):
        return None
    if not media.get("downloaded"):
        return None
    return resolve_under_data_dir(settings, media.get("path"))


async def fetch_file_from_telegram(
    client: TelegramClient,
    conn: Any,
    settings: Settings,
    *,
    kind: str,
    ident: str,
) -> tuple[Path, str, str]:
    sources = await lookup_file_sources(conn, kind=kind, ident=ident)
    if not sources:
        raise FileUnavailable(404, "File not found")
    last_error: Exception | None = None
    dest = settings.data_dir / "tmp" / "media" / f"file-{uuid.uuid4().hex}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    for row in sources:
        peer_id = int(row["peer_external_id"])
        msg_id = row.get("telegram_message_id")
        if msg_id is None:
            continue
        media = row.get("media") if isinstance(row.get("media"), dict) else {}
        try:
            entity = await entity_for_peer(client, conn, peer_id)
            got = await client.get_messages(entity, ids=int(msg_id))
        except FloodWaitError:
            dest.unlink(missing_ok=True)
            raise
        except Exception as exc:
            last_error = exc
            lg.info("telegram file skip peer %s msg %s: %s", peer_id, msg_id, exc)
            continue
        message = got[0] if isinstance(got, list) else got
        if not isinstance(message, Message):
            continue
        try:
            saved = await client.download_media(message, file=str(dest))
        except FloodWaitError:
            dest.unlink(missing_ok=True)
            raise
        except Exception as exc:
            last_error = exc
            dest.unlink(missing_ok=True)
            continue
        path = Path(saved) if saved else dest
        if not path.is_file() or path.stat().st_size <= 0:
            path.unlink(missing_ok=True)
            continue
        mime = str(media.get("mime_type") or "") if isinstance(media, dict) else ""
        name = safe_filename(
            str(media.get("file_name") or "") if isinstance(media, dict) else None,
            mime=mime,
        )
        return path, name, content_type_for_file(mime, path)
    dest.unlink(missing_ok=True)
    detail = "Could not download this file from Telegram"
    if last_error is not None:
        lg.warning("telegram file download failed for %s: %s", ident, last_error)
    raise FileUnavailable(404, detail)
