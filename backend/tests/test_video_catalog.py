from __future__ import annotations

from datetime import datetime, timezone

from telethon.tl.types import (
    Document,
    DocumentAttributeFilename,
    DocumentAttributeVideo,
    MessageMediaDocument,
)

from telegram_snowball.bytesfmt import format_bytes
from telegram_snowball.telegram.media_kinds import classify_message_media
from telegram_snowball.telegram.video_files import VideoUnavailable, parse_video_id, safe_filename, video_file_url


def test_format_bytes() -> None:
    assert format_bytes(0) == "0 B"
    assert format_bytes(512) == "512 B"
    assert format_bytes(1024) == "1 KB"
    assert format_bytes(1536) == "1.5 KB"
    assert format_bytes(12_582_912) == "12 MB"
    assert format_bytes(1_073_741_824) == "1 GB"
    assert format_bytes(None) is None


def test_video_file_identity() -> None:
    assert parse_video_id("987654321") == ("document", "987654321")
    assert parse_video_id("msg:11111111-1111-1111-1111-111111111111") == (
        "message",
        "11111111-1111-1111-1111-111111111111",
    )
    assert video_file_url("987654321") == "/api/videos/987654321/file"
    assert (
        video_file_url("msg:11111111-1111-1111-1111-111111111111")
        == "/api/videos/msg/11111111-1111-1111-1111-111111111111/file"
    )
    assert safe_filename("clip.mp4") == "clip.mp4"
    assert safe_filename("../evil.mp4") == "evil.mp4"
    assert safe_filename(None, mime="video/webm") == "video.webm"
    try:
        parse_video_id("not-a-video")
    except VideoUnavailable as exc:
        assert exc.status == 404
    else:
        raise AssertionError("expected VideoUnavailable")


def test_classify_video_document_fields() -> None:
    doc = Document(
        id=9876543210123,
        access_hash=1,
        file_reference=b"ab",
        date=datetime.now(timezone.utc),
        mime_type="video/mp4",
        size=12_582_912,
        dc_id=2,
        attributes=[
            DocumentAttributeVideo(
                duration=125,
                w=1280,
                h=720,
                round_message=False,
                supports_streaming=True,
            ),
            DocumentAttributeFilename(file_name="news.mp4"),
        ],
    )
    classified = classify_message_media(MessageMediaDocument(document=doc))
    assert classified is not None
    assert classified["kind"] == "video"
    assert classified["document_id"] == "9876543210123"
    assert classified["size_bytes"] == 12_582_912
    assert classified["duration"] == 125
    assert classified["width"] == 1280
    assert classified["height"] == 720
    assert classified["file_name"] == "news.mp4"
    assert classified["mime_type"] == "video/mp4"
    assert classified["downloaded"] is False
