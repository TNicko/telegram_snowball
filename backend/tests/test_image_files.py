from __future__ import annotations

from pathlib import Path

from telegram_snowball.config import Settings
from telegram_snowball.telegram.image_files import resolve_under_data_dir


def test_resolve_under_data_dir_requires_local_file(tmp_path: Path) -> None:
    settings = Settings(snowball_data_dir=tmp_path, postgres_dsn="postgresql://unused")
    blob = tmp_path / "blobs" / "images" / "ab" / "abcd.jpg"
    blob.parent.mkdir(parents=True)
    blob.write_bytes(b"x")
    assert resolve_under_data_dir(settings, "blobs/images/ab/abcd.jpg") == blob.resolve()
    assert resolve_under_data_dir(settings, "https://example.com/x.jpg") is None
    assert resolve_under_data_dir(settings, "") is None
    assert resolve_under_data_dir(settings, None) is None
