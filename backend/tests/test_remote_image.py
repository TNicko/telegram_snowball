from __future__ import annotations

import pytest

from telegram_snowball.config import Settings
from telegram_snowball.telegram.image_files import resolve_under_data_dir
from telegram_snowball.telegram.remote_image import is_remote_image_ref, parse_s3_uri, presign_s3_get


def test_remote_ref_prefixes() -> None:
    assert is_remote_image_ref("s3://bucket/key.jpg")
    assert is_remote_image_ref("https://example.com/x.jpg")
    assert not is_remote_image_ref("blobs/images/ab/abcd.jpg")
    assert not is_remote_image_ref("")
    assert not is_remote_image_ref(None)


def test_parse_s3_uri() -> None:
    assert parse_s3_uri("s3://example-bucket/foo/bar.jpg") == (
        "example-bucket",
        "foo/bar.jpg",
    )
    with pytest.raises(ValueError):
        parse_s3_uri("https://example.com/x")


def test_resolve_under_data_dir_skips_remote(tmp_path) -> None:
    settings = Settings(snowball_data_dir=tmp_path, postgres_dsn="postgresql://unused")
    assert resolve_under_data_dir(settings, "s3://bucket/key.jpg") is None
    assert resolve_under_data_dir(settings, "https://example.com/x.jpg") is None


def test_presign_requires_keys(monkeypatch) -> None:
    monkeypatch.delenv("AWS_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("AWS_SECRET_ACCESS_KEY", raising=False)
    with pytest.raises(RuntimeError, match="AWS_ACCESS_KEY_ID"):
        presign_s3_get("s3://bucket/key.jpg")
