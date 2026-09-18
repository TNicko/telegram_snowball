from __future__ import annotations

from typing import Any

from telethon.tl.types import (
    DocumentAttributeAnimated,
    DocumentAttributeAudio,
    DocumentAttributeSticker,
    DocumentAttributeVideo,
    MessageMediaDocument,
    MessageMediaPhoto,
)


def classify_message_media(media: Any) -> dict[str, Any] | None:
    """Slim media record stored on ``messages.media`` — kind from Telethon, not downloads."""
    if media is None:
        return None
    tl = type(media).__name__
    kind, size_bytes = _kind_and_size(media)
    out: dict[str, Any] = {"tl": tl, "downloaded": False}
    if kind:
        out["kind"] = kind
    if size_bytes is not None:
        out["size_bytes"] = int(size_bytes)
    return out


def _kind_and_size(media: Any) -> tuple[str | None, int | None]:
    if isinstance(media, MessageMediaPhoto):
        return "image", None
    if not isinstance(media, MessageMediaDocument):
        return None, None
    doc = getattr(media, "document", None)
    if doc is None:
        return None, None
    size = getattr(doc, "size", None)
    mime = (getattr(doc, "mime_type", None) or "").lower()
    attrs = list(getattr(doc, "attributes", None) or [])
    if any(isinstance(item, DocumentAttributeSticker) for item in attrs):
        if mime.startswith("image/") and "svg" not in mime:
            return "image", size
        return None, size
    if any(isinstance(item, DocumentAttributeAnimated) for item in attrs) or mime == "image/gif":
        return "gif", size
    if any(isinstance(item, DocumentAttributeAudio) for item in attrs) or mime.startswith("audio/"):
        return "audio", size
    if any(isinstance(item, DocumentAttributeVideo) for item in attrs) or mime.startswith("video/"):
        return "video", size
    if mime.startswith("image/") and "svg" not in mime and "dwg" not in mime:
        return "image", size
    return "document", size


def media_kind_from_stored(media: Any) -> str | None:
    if not isinstance(media, dict):
        return None
    kind = media.get("kind")
    if kind in ("image", "gif", "video", "audio", "document"):
        return kind
    if media.get("tl") == "MessageMediaPhoto":
        return "image"
    if media.get("tl") == "MessageMediaDocument":
        return "document"
    return None
