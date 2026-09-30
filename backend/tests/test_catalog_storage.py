from __future__ import annotations

from pathlib import Path

from telegram_snowball.catalog_storage import _bucket, directory_bytes


def test_directory_bytes_sums_nested_files(tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "one.bin").write_bytes(b"abcd")
    (tmp_path / "a" / "two.bin").write_bytes(b"efghij")
    (tmp_path / "empty").mkdir()
    assert directory_bytes(tmp_path) == 10
    assert directory_bytes(tmp_path / "missing") == 0


def test_bucket_labels_zero() -> None:
    body = _bucket(0, 0)
    assert body["count"] == 0
    assert body["bytes"] == 0
    assert body["bytes_label"] == "0 B"
    empty_table = _bucket(0, 65536)
    assert empty_table["count"] == 0
    assert empty_table["bytes"] == 0
    assert empty_table["bytes_label"] == "0 B"
    sized = _bucket(12, 1024)
    assert sized["count"] == 12
    assert sized["bytes_label"] == "1 KB"
