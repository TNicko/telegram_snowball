from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from telethon import TelegramClient
from telethon.errors import FloodWaitError, ForbiddenError, UserPrivacyRestrictedError
from telethon.tl.types import Photo, PhotoEmpty, VideoSize

from telegram_snowball.config import Settings

lg = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class HarvestedProfilePhoto:
    rel_path: str
    media_kind: str
    content_type: str


def _prefix(peer_type: str) -> str:
    if peer_type in ("user", "bot"):
        return "users/telegram"
    return "communities/telegram"


def _thumb_sort_key(thumb: Any) -> tuple[int, int]:
    tl = getattr(thumb, "tl", None) or getattr(thumb, "_", None)
    if tl in ("PhotoStrippedSize", "PhotoCachedSize"):
        data = getattr(thumb, "bytes", None) or getattr(thumb, "data", None) or b""
        return 1, len(data)
    if tl == "PhotoSize":
        return 1, int(getattr(thumb, "size", 0) or 0)
    if tl == "PhotoSizeProgressive":
        sizes = getattr(thumb, "sizes", None) or []
        return 1, max(sizes) if sizes else 0
    if tl == "VideoSize" or isinstance(thumb, VideoSize):
        return 2, int(getattr(thumb, "size", 0) or 0)
    return 0, 0


def _largest_thumb(photo: Photo) -> Any | None:
    thumbs = list(photo.sizes or []) + list(photo.video_sizes or [])
    if not thumbs:
        return None
    thumbs = sorted(thumbs, key=_thumb_sort_key)
    return thumbs[-1]


def resolve_profile_photo_variant(photo: Photo) -> tuple[str, str, str]:
    """Return ``(ext, content_type, media_kind)`` — same rules as messenger."""
    thumb = _largest_thumb(photo)
    if isinstance(thumb, VideoSize):
        return "mp4", "video/mp4", "video"

    video_sizes = list(photo.video_sizes or [])
    has_video_size = any(isinstance(item, VideoSize) for item in video_sizes)
    if video_sizes and not has_video_size:
        lg.warning(
            "Profile photo id=%s has video markup without VideoSize; falling back to static image",
            photo.id,
        )
    return "jpg", "image/jpeg", "image"


def sniff_media_bytes(data: bytes) -> tuple[str | None, str | None]:
    """Detect raster image vs video from magic bytes."""
    head = data[:16]
    if head.startswith(b"\xff\xd8"):
        return "image", "image/jpeg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image", "image/png"
    if head.startswith(b"GIF8"):
        return "image", "image/gif"
    if head.startswith(b"RIFF") and b"WEBP" in head:
        return "image", "image/webp"
    if len(head) >= 8 and head[4:8] == b"ftyp":
        return "video", "video/mp4"
    if head.startswith(b"\x1aE\xdf\xa3"):
        return "video", "video/webm"
    return None, None


def sniff_profile_media(path: Path) -> tuple[str | None, str | None]:
    """Detect image vs looping video avatar from file bytes, not the extension."""
    try:
        head = path.read_bytes()[:16]
    except OSError:
        return None, None
    return sniff_media_bytes(head)


def suffix_for_content_type(content_type: str | None) -> str:
    return {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/gif": ".gif",
        "image/webp": ".webp",
    }.get(content_type or "", ".jpg")


def is_raster_image(path: Path) -> bool:
    kind, _content_type = sniff_profile_media(path)
    return kind == "image"


async def harvest_profile_photo(
    client: TelegramClient,
    *,
    settings: Settings,
    entity: Any,
    peer_type: str,
    external_id: int,
) -> HarvestedProfilePhoto | None:
    """Download the current profile photo, including Telegram video/animated avatars."""
    try:
        photos = await client.get_profile_photos(entity, limit=1)
    except FloodWaitError:
        raise
    except (UserPrivacyRestrictedError, ForbiddenError) as exc:
        lg.info("profile photo forbidden for %s %s: %s", peer_type, external_id, exc)
        return None
    except Exception as exc:
        lg.warning("get_profile_photos failed for %s %s: %s", peer_type, external_id, exc)
        return None
    if not photos:
        return None
    photo = photos[0]
    if isinstance(photo, PhotoEmpty) or not isinstance(photo, Photo):
        return None
    photo_id = getattr(photo, "id", None)
    if photo_id is None:
        return None
    ext, content_type, media_kind = resolve_profile_photo_variant(photo)
    rel = Path(_prefix(peer_type)) / str(external_id) / "profile_photos" / f"{int(photo_id)}.{ext}"
    dest = settings.data_dir / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        saved = await client.download_media(photo, file=str(dest))
    except FloodWaitError:
        raise
    except Exception as exc:
        lg.warning("download profile photo failed for %s %s: %s", peer_type, external_id, exc)
        return None
    if not saved:
        return None
    saved_path = Path(saved)
    sniffed_kind, sniffed_type = sniff_profile_media(saved_path)
    if sniffed_kind:
        media_kind = sniffed_kind
        content_type = sniffed_type or content_type
        if sniffed_kind == "video" and saved_path.suffix.lower() != ".mp4":
            renamed = saved_path.with_suffix(".mp4")
            saved_path.replace(renamed)
            saved_path = renamed
            rel = saved_path.relative_to(settings.data_dir)
    elif media_kind not in ("image", "video"):
        saved_path.unlink(missing_ok=True)
        return None
    return HarvestedProfilePhoto(
        rel_path=str(rel),
        media_kind=media_kind,
        content_type=content_type,
    )
