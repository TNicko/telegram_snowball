from __future__ import annotations

from types import SimpleNamespace

from telethon.tl.types import PeerChannel, PeerChat, PeerUser

from telegram_snowball.telegram.forwards import fwd_from_name, signed_peer_from_fwd
from telegram_snowball.telegram.ids import (
    CHANNEL_MARK,
    channel_id_from_signed_peer_id,
    infer_peer_type_from_signed,
    input_peer_from_stored,
    is_snowball_target,
    signed_peer_id_from_raw_channel_id,
)


def test_parse_max_depth_zero_is_seed_only() -> None:
    from telegram_snowball.jobs.forward_snowball import _parse_max_depth

    assert _parse_max_depth(None) is None
    assert _parse_max_depth("") is None
    assert _parse_max_depth(0) == 0
    assert _parse_max_depth("0") == 0
    assert _parse_max_depth(2) == 2


def test_has_image_phash() -> None:
    from telegram_snowball.jobs.forward_snowball import _has_image_phash

    assert not _has_image_phash(None)
    assert not _has_image_phash({"kind": "image"})
    assert _has_image_phash({"kind": "image", "phash": "abcd1234"})


def test_message_in_date_range() -> None:
    from datetime import datetime, timezone

    from telegram_snowball.jobs.forward_snowball import _message_in_date_range, _parse_job_datetime

    start = _parse_job_datetime("2024-06-01T00:00:00.000Z")
    end = _parse_job_datetime("2024-06-30T23:59:59.999Z")
    inside = SimpleNamespace(date=datetime(2024, 6, 15, tzinfo=timezone.utc))
    before = SimpleNamespace(date=datetime(2024, 5, 31, 23, 59, tzinfo=timezone.utc))
    after = SimpleNamespace(date=datetime(2024, 7, 1, tzinfo=timezone.utc))
    assert _message_in_date_range(inside, None, None)
    assert _message_in_date_range(inside, start, end)
    assert not _message_in_date_range(before, start, end)
    assert not _message_in_date_range(after, start, end)
    assert not _message_in_date_range(SimpleNamespace(date=None), start, end)


def test_signed_peer_helpers() -> None:
    raw = 1293233260
    signed = signed_peer_id_from_raw_channel_id(raw)
    assert signed == -(CHANNEL_MARK + raw)
    assert channel_id_from_signed_peer_id(signed) == raw
    assert infer_peer_type_from_signed(signed) == "channel"
    assert is_snowball_target(signed)


def test_basic_chat_and_user_ids() -> None:
    assert infer_peer_type_from_signed(-12345) == "chat"
    assert is_snowball_target(-12345)
    assert infer_peer_type_from_signed(42) == "user"
    assert not is_snowball_target(42)
    assert channel_id_from_signed_peer_id(-12345) is None
    assert channel_id_from_signed_peer_id(42) is None


def test_input_peer_from_stored_channel() -> None:
    raw = 99
    signed = signed_peer_id_from_raw_channel_id(raw)
    peer = input_peer_from_stored(
        external_id=signed,
        peer_type="channel",
        access_hash=555,
    )
    assert peer is not None
    assert peer.channel_id == raw
    assert peer.access_hash == 555
    assert (
        input_peer_from_stored(external_id=signed, peer_type="channel", access_hash=None)
        is None
    )


def test_signed_from_fwd_channel_and_saved_from() -> None:
    raw = 777
    fwd = SimpleNamespace(
        from_id=PeerChannel(raw),
        saved_from_peer=None,
        from_name="News",
    )
    assert signed_peer_from_fwd(fwd) == signed_peer_id_from_raw_channel_id(raw)
    assert fwd_from_name(fwd) == "News"

    chat_fwd = SimpleNamespace(from_id=None, saved_from_peer=PeerChat(88), from_name=None)
    assert signed_peer_from_fwd(chat_fwd) == -88

    user_fwd = SimpleNamespace(from_id=PeerUser(9), saved_from_peer=None, from_name="A")
    assert signed_peer_from_fwd(user_fwd) == 9
    assert not is_snowball_target(signed_peer_from_fwd(user_fwd) or 0)

    stored = {
        "_": "MessageFwdHeader",
        "from_id": {"_": "PeerChannel", "channel_id": raw},
        "from_name": "News",
    }
    assert signed_peer_from_fwd(stored) == signed_peer_id_from_raw_channel_id(raw)
    assert fwd_from_name(stored) == "News"


def test_origin_telegram_id_from_fwd() -> None:
    from telegram_snowball.telegram.forwards import origin_telegram_id_from_fwd

    assert origin_telegram_id_from_fwd(None) is None
    assert origin_telegram_id_from_fwd({"channel_post": 88}) == 88
    assert origin_telegram_id_from_fwd({"saved_from_msg_id": 12}) == 12
    assert origin_telegram_id_from_fwd({"channel_post": "0"}) is None
