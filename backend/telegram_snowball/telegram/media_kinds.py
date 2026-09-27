from __future__ import annotations

from typing import Any

from telethon.tl.types import (
    DocumentAttributeAnimated,
    DocumentAttributeAudio,
    DocumentAttributeFilename,
    DocumentAttributeImageSize,
    DocumentAttributeSticker,
    DocumentAttributeVideo,
    MessageMediaDocument,
    MessageMediaPhoto,
)

_IMAGE_EXTS = frozenset({
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".bmp",
    ".tif",
    ".tiff",
    ".heic",
    ".heif",
    ".avif",
    ".jfif",
})
_VIDEO_EXTS = frozenset({".mp4", ".m4v", ".mov", ".mkv", ".webm", ".avi", ".3gp", ".mpeg", ".mpg"})
_GIF_EXTS = frozenset({".gif"})
_AUDIO_EXTS = frozenset({".mp3", ".m4a", ".ogg", ".oga", ".flac", ".wav", ".opus", ".aac"})
_KNOWN_KINDS = frozenset({"image", "gif", "video", "audio", "document"})


def _file_ext(name: str | None) -> str:
    raw = (name or "").replace("\\", "/").rsplit("/", 1)[-1].strip()
    if "." not in raw:
        return ""
    return "." + raw.rsplit(".", 1)[-1].lower()


def kind_from_document_hints(
    *,
    mime_type: str | None = None,
    file_name: str | None = None,
    attributes: list[Any] | None = None,
) -> str | None:
    """Classify a Telegram document from mime, filename, and TL attributes."""
    mime = (mime_type or "").strip().lower()
    attrs = list(attributes or [])
    if any(isinstance(item, DocumentAttributeSticker) for item in attrs):
        if mime.startswith("image/") and "svg" not in mime:
            return "image"
        return None
    if any(isinstance(item, DocumentAttributeAnimated) for item in attrs) or mime == "image/gif":
        return "gif"
    if any(isinstance(item, DocumentAttributeAudio) for item in attrs) or mime.startswith("audio/"):
        return "audio"
    if any(isinstance(item, DocumentAttributeVideo) for item in attrs) or mime.startswith("video/"):
        return "video"
    if any(isinstance(item, DocumentAttributeImageSize) for item in attrs):
        return "image"
    if mime.startswith("image/") and "svg" not in mime and "dwg" not in mime:
        return "image"
    ext = _file_ext(file_name)
    if ext in _GIF_EXTS:
        return "gif"
    if ext in _IMAGE_EXTS:
        return "image"
    if ext in _VIDEO_EXTS:
        return "video"
    if ext in _AUDIO_EXTS:
        return "audio"
    return "document"


def document_catalog_fields(doc: Any) -> dict[str, Any]:
    """Stable Telegram document fields used by the media catalogs."""
    out: dict[str, Any] = {}
    doc_id = getattr(doc, "id", None)
    if doc_id is not None:
        out["document_id"] = str(int(doc_id))
    mime = getattr(doc, "mime_type", None)
    if mime:
        out["mime_type"] = str(mime)
    for attr in getattr(doc, "attributes", None) or []:
        if isinstance(attr, (DocumentAttributeVideo, DocumentAttributeImageSize)):
            duration = getattr(attr, "duration", None)
            if duration is not None:
                out["duration"] = int(duration)
            width = getattr(attr, "w", None)
            if width:
                out["width"] = int(width)
            height = getattr(attr, "h", None)
            if height:
                out["height"] = int(height)
        elif isinstance(attr, DocumentAttributeFilename):
            name = getattr(attr, "file_name", None)
            if name:
                out["file_name"] = str(name)
    return out


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
    if isinstance(media, MessageMediaDocument):
        doc = getattr(media, "document", None)
        if doc is not None:
            out.update(document_catalog_fields(doc))
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
    fields = document_catalog_fields(doc)
    kind = kind_from_document_hints(
        mime_type=fields.get("mime_type") or getattr(doc, "mime_type", None),
        file_name=fields.get("file_name"),
        attributes=list(getattr(doc, "attributes", None) or []),
    )
    return kind, size


def media_kind_from_stored(media: Any) -> str | None:
    if not isinstance(media, dict):
        return None
    kind = media.get("kind")
    if kind in ("image", "gif", "video", "audio"):
        return kind
    mime = str(media.get("mime_type") or "")
    name = str(media.get("file_name") or "")
    if mime or name or kind == "document" or media.get("tl") == "MessageMediaDocument":
        inferred = kind_from_document_hints(mime_type=mime or None, file_name=name or None)
        if inferred in _KNOWN_KINDS:
            return inferred
    if media.get("tl") == "MessageMediaPhoto":
        return "image"
    return None
