from __future__ import annotations

from telegram_snowball.api.routes.messages import media_preview, message_detail


def test_media_preview_image_uses_phash_file_url() -> None:
    preview = media_preview(
        {"kind": "image", "phash": "abc123", "size_bytes": 2048, "width": 640, "height": 480},
        kind="image",
    )
    assert preview is not None
    assert preview["kind"] == "image"
    assert preview["file_url"] == "/api/images/abc123/file"
    assert preview["size_label"] == "2 KB"
    assert preview["width"] == 640
    assert preview["height"] == 480


def test_media_preview_video_has_no_file_url() -> None:
    preview = media_preview(
        {
            "kind": "video",
            "size_bytes": 1024 * 1024,
            "duration": 12.4,
            "mime_type": "video/mp4",
            "file_name": "clip.mp4",
        },
        kind="video",
    )
    assert preview is not None
    assert preview["kind"] == "video"
    assert preview["file_url"] is None
    assert preview["size_label"] == "1 MB"
    assert preview["duration"] == 12.4
    assert preview["file_name"] == "clip.mp4"


def test_message_detail_returns_full_content() -> None:
    body = "x" * 2500
    detail = message_detail(
        {
            "id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            "telegram_message_id": 9,
            "date": "2026-01-02T00:00:00+00:00",
            "content": body,
            "media": {"kind": "document", "mime_type": "application/pdf", "size_bytes": 4096},
        }
    )
    assert detail["content"] == body
    assert detail["media_kind"] == "document"
    assert detail["media"]["file_url"] is None
    assert detail["media"]["mime_type"] == "application/pdf"
