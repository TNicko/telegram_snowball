"""On-demand Telegram video download for the catalog (never auto-played)."""

from __future__ import annotations

import logging
import re
import uuid
from pathlib import Path
from typing import Any

from telethon import TelegramClient
from telethon.errors import FloodWaitError
from telethon.tl.types import Message

from telegram_snowball.config import Settings
from telegram_snowball.catalog import stored_kind_is
from telegram_snowball.telegram.image_files import resolve_under_data_dir
from telegram_snowball.telegram.resolve import entity_for_peer

lg = logging.getLogger(__name__)

_DOC_ID_RE = re.compile(r"^[0-9]+$")
_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


class VideoUnavailable(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


def parse_video_id(video_id: str) -> tuple[str, str]:
    """Return ``('document', id)`` or ``('message', uuid)``."""
    raw = (video_id or "").strip()
    if raw.lower().startswith("msg:"):
        raw = raw[4:]
    if _DOC_ID_RE.fullmatch(raw):
        return "document", raw
    if _UUID_RE.fullmatch(raw):
        return "message", raw.lower()
    raise VideoUnavailable(404, "Video not found")


def video_file_url(video_id: str) -> str:
    kind, ident = parse_video_id(video_id)
    if kind == "message":
        return f"/api/videos/msg/{ident}/file"
    return f"/api/videos/{ident}/file"


def safe_filename(name: str | None, *, mime: str | None = None) -> str:
    raw = (name or "").replace("\\", "/").rsplit("/", 1)[-1].strip()
    cleaned = "".join(ch for ch in raw if ch.isprintable() and ch not in '<>:"|?*')
    cleaned = cleaned.strip(" .")
    if cleaned:
        return cleaned[:180]
    if mime and "webm" in mime:
        return "video.webm"
    if mime and "quicktime" in mime:
        return "video.mov"
    return "video.mp4"


def content_type_for_video(mime: str | None, path: Path | None = None) -> str:
    if mime and mime.startswith("video/"):
        return mime
    suffix = path.suffix.lower() if path is not None else ""
    return {
        ".webm": "video/webm",
        ".mov": "video/quicktime",
        ".mkv": "video/x-matroska",
    }.get(suffix, "video/mp4")


async def lookup_video_sources(
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
            WHERE {stored_kind_is("video")}
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
              AND {stored_kind_is("video")}
            """,
            (ident,),
        )
    return [dict(row) for row in await rows.fetchall()]


def persisted_video_path(settings: Settings, media: dict[str, Any] | None) -> Path | None:
    if not isinstance(media, dict):
        return None
    if not media.get("downloaded"):
        return None
    return resolve_under_data_dir(settings, media.get("path"))


async def fetch_video_from_telegram(
    client: TelegramClient,
    conn: Any,
    settings: Settings,
    *,
    kind: str,
    ident: str,
) -> tuple[Path, str, str]:
    sources = await lookup_video_sources(conn, kind=kind, ident=ident)
    if not sources:
        raise VideoUnavailable(404, "Video not found")
    last_error: Exception | None = None
    dest = settings.data_dir / "tmp" / "media" / f"video-{uuid.uuid4().hex}"
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
            lg.info("telegram video skip peer %s msg %s: %s", peer_id, msg_id, exc)
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
        if path.suffix.lower() not in {".mp4", ".webm", ".mov", ".mkv"} and name.endswith(".mp4"):
            renamed = path.with_suffix(".mp4")
            path.replace(renamed)
            path = renamed
        return path, name, content_type_for_video(mime, path)
    dest.unlink(missing_ok=True)
    detail = "Could not download this video from Telegram"
    if last_error is not None:
        lg.warning("telegram video download failed for %s: %s", ident, last_error)
    raise VideoUnavailable(404, detail)
