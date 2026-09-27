from __future__ import annotations

from datetime import datetime, timezone

from telegram_snowball.api.routes.graph import (
    IMAGE_GRAPH_LIMIT,
    MIN_SHARED_IMAGE_PEERS,
    _image_node,
    shared_image_date_sql,
)


def test_shared_image_date_sql_empty() -> None:
    sql, params = shared_image_date_sql(date_from=None, date_to=None)
    assert sql == "TRUE"
    assert params == []


def test_shared_image_date_sql_bounds() -> None:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    end = datetime(2026, 2, 1, tzinfo=timezone.utc)
    sql, params = shared_image_date_sql(date_from=start, date_to=end)
    assert "ibm.message_date >= %s" in sql
    assert "ibm.message_date <= %s" in sql
    assert params == [start, end]


def test_image_node_shape() -> None:
    node = _image_node(phash="abcd1234abcd1234", unique_peers=4, appearances=12, first_seen=None)
    assert node["id"] == "img:abcd1234abcd1234"
    assert node["kind"] == "image"
    assert node["degree"] == 4
    assert node["forward_volume"] == 12
    assert node["photo_url"] == "/api/images/abcd1234abcd1234/file"
    assert node["media_kind"] == "image"
    assert IMAGE_GRAPH_LIMIT >= 1
    assert MIN_SHARED_IMAGE_PEERS == 2
