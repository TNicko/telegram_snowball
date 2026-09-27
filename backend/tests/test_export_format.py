from __future__ import annotations

from telegram_snowball.export.files import csv_cell, write_csv, write_zip
from telegram_snowball.export.peers import flatten_peer_csv


def test_csv_cell_bool_and_none() -> None:
    assert csv_cell(None) == ""
    assert csv_cell(True) == "true"
    assert csv_cell(False) == "false"


def test_write_csv_utf8_bom_and_header() -> None:
    data = write_csv([{"a": "x", "b": 1}], ["a", "b"])
    assert data.startswith(b"\xef\xbb\xbf")
    assert b"a,b" in data
    assert b"x,1" in data


def test_zip_omits_empty_bytes() -> None:
    archive = write_zip({"keep.csv": b"a\n", "skip.csv": b""})
    assert archive[:2] == b"PK"


def test_flatten_peer_csv_usernames_and_media() -> None:
    row = flatten_peer_csv(
        {
            "external_id": 1,
            "peer_type": "channel",
            "title": "News",
            "username": "news",
            "usernames": [
                {"username": "news", "active": True},
                {"username": "old", "active": False},
            ],
            "media": {"image": {"total": 10, "downloaded": 2}, "video": None},
            "posts": 5,
        }
    )
    assert row["usernames"] == "news;old"
    assert row["images_unique"] == 10
    assert row["images_persisted"] == 2
    assert row["videos_total"] is None
