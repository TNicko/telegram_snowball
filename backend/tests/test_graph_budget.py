from __future__ import annotations

from datetime import datetime, timezone

from telegram_snowball.api.routes.graph import (
    AUTO_NODES,
    CONFIRM_NODES,
    budget_band,
    estimate_graph_bytes,
    fwd_origin_match_sql,
    message_filter_sql,
    message_scope_is_open,
    parse_media_param,
)
from telegram_snowball.telegram.ids import signed_peer_id_from_raw_channel_id


def test_parse_media_param_all_or_none() -> None:
    assert parse_media_param(None) is None
    assert parse_media_param("none,image,video,audio,gif,document") is None
    assert parse_media_param("") == set()
    assert parse_media_param("image,video") == {"image", "video"}
    assert parse_media_param("none") == {"none"}


def test_budget_band_thresholds() -> None:
    assert budget_band(10, 10, 1_000) == "auto"
    assert budget_band(AUTO_NODES + 1, 10, 1_000) == "confirm"
    assert budget_band(CONFIRM_NODES + 1, 10, 1_000) == "block"
    assert estimate_graph_bytes(2, 3, 4) > 0


def test_message_scope_is_open() -> None:
    assert message_scope_is_open(None, None, None) is True
    assert message_scope_is_open(-1, None, None) is False
    now = datetime.now(timezone.utc)
    assert message_scope_is_open(None, now, None) is False


def test_fwd_origin_match_sql_channel() -> None:
    peer_id = signed_peer_id_from_raw_channel_id(99)
    sql, params = fwd_origin_match_sql(peer_id)
    assert "PeerChannel" in sql
    assert params == [99, 99]


def test_fwd_origin_match_sql_chat_and_user() -> None:
    chat_sql, chat_params = fwd_origin_match_sql(-88)
    assert "PeerChat" in chat_sql
    assert chat_params == [88, 88]
    user_sql, user_params = fwd_origin_match_sql(42)
    assert "PeerUser" in user_sql
    assert user_params == [42, 42]


def test_message_filter_sql_neighborhood_and_media() -> None:
    sql, params = message_filter_sql(
        peer_id=-100,
        date_from=None,
        date_to=None,
        media={"image"},
    )
    assert "m.peer_external_id = %s" in sql
    assert params[0] == -100
    assert "ANY(%s)" in sql
    assert params[-1] == ["image"]
