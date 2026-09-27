from __future__ import annotations

from datetime import datetime, timezone

from telethon.tl.types import (
    Document,
    DocumentAttributeFilename,
    DocumentAttributeImageSize,
    DocumentAttributeVideo,
    MessageMediaDocument,
    MessageMediaPhoto,
)

from telegram_snowball.telegram.media_kinds import classify_message_media, media_kind_from_stored


def _doc(**overrides: object) -> Document:
    now = datetime.now(timezone.utc)
    fields = dict(
        id=1,
        access_hash=1,
        file_reference=b"ab",
        date=now,
        mime_type="application/octet-stream",
        size=100,
        dc_id=2,
        attributes=[],
    )
    fields.update(overrides)
    return Document(**fields)


def test_image_document_from_image_size_attr() -> None:
    classified = classify_message_media(
        MessageMediaDocument(
            document=_doc(
                mime_type="application/octet-stream",
                attributes=[
                    DocumentAttributeImageSize(w=800, h=600),
                    DocumentAttributeFilename(file_name="scan.jpg"),
                ],
            )
        )
    )
    assert classified is not None
    assert classified["kind"] == "image"
    assert classified["width"] == 800
    assert classified["height"] == 600
    assert classified["file_name"] == "scan.jpg"


def test_image_document_from_filename() -> None:
    classified = classify_message_media(
        MessageMediaDocument(
            document=_doc(
                attributes=[DocumentAttributeFilename(file_name="photo.PNG")],
            )
        )
    )
    assert classified is not None
    assert classified["kind"] == "image"


def test_video_document_from_filename() -> None:
    classified = classify_message_media(
        MessageMediaDocument(
            document=_doc(
                attributes=[DocumentAttributeFilename(file_name="clip.mp4")],
            )
        )
    )
    assert classified is not None
    assert classified["kind"] == "video"


def test_pdf_stays_document() -> None:
    classified = classify_message_media(
        MessageMediaDocument(
            document=_doc(
                mime_type="application/pdf",
                attributes=[DocumentAttributeFilename(file_name="notes.pdf")],
            )
        )
    )
    assert classified is not None
    assert classified["kind"] == "document"


def test_photo_media_is_image() -> None:
    classified = classify_message_media(MessageMediaPhoto(photo=None))
    assert classified is not None
    assert classified["kind"] == "image"


def test_stored_document_image_mime_is_image() -> None:
    assert (
        media_kind_from_stored(
            {
                "tl": "MessageMediaDocument",
                "kind": "document",
                "mime_type": "image/jpeg",
                "file_name": "a.jpg",
            }
        )
        == "image"
    )


def test_stored_document_video_filename_is_video() -> None:
    assert (
        media_kind_from_stored(
            {
                "tl": "MessageMediaDocument",
                "kind": "document",
                "mime_type": "application/octet-stream",
                "file_name": "clip.MOV",
            }
        )
        == "video"
    )


def test_stored_webpage_is_not_a_document() -> None:
    assert media_kind_from_stored({"tl": "MessageMediaWebPage"}) is None


def test_video_attribute_still_wins() -> None:
    classified = classify_message_media(
        MessageMediaDocument(
            document=_doc(
                mime_type="video/mp4",
                attributes=[
                    DocumentAttributeVideo(duration=3, w=10, h=10, round_message=False, supports_streaming=True),
                    DocumentAttributeFilename(file_name="x.mp4"),
                ],
            )
        )
    )
    assert classified is not None
    assert classified["kind"] == "video"
