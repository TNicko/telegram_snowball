from __future__ import annotations

from types import SimpleNamespace

from telegram_snowball.telegram.ids import signed_peer_id_from_raw_channel_id
from telegram_snowball.telegram.profile import (
    full_profile_from_full,
    min_profile_from_entity,
    restriction_reason_csv,
    usernames_csv,
    usernames_from_entity,
)


def test_usernames_primary_first_and_aliases() -> None:
    entity = SimpleNamespace(
        username="MainHandle",
        usernames=[
            SimpleNamespace(username="oldname", active=False, editable=False),
            SimpleNamespace(username="MainHandle", active=True, editable=True),
            SimpleNamespace(username="alias", active=True, editable=False),
        ],
    )
    rows = usernames_from_entity(entity)
    assert [row["username"] for row in rows] == ["MainHandle", "oldname", "alias"]
    assert rows[0]["active"] is True
    assert rows[0]["editable"] is True
    assert usernames_csv(rows) == "MainHandle;oldname;alias"


def test_usernames_primary_only() -> None:
    entity = SimpleNamespace(username="solo", usernames=None)
    rows = usernames_from_entity(entity)
    assert rows == [{"username": "solo", "active": True}]


def test_min_profile_channel_flags() -> None:
    entity = SimpleNamespace(
        title="News",
        username="news",
        usernames=[],
        date=None,
        first_name=None,
        last_name=None,
        verified=True,
        scam=False,
        fake=False,
        restricted=False,
        restriction_reason=[],
        noforwards=True,
        forum=False,
        gigagroup=False,
        join_to_send=True,
        join_request=False,
        has_link=True,
        has_geo=False,
        deleted=None,
        premium=None,
        deactivated=None,
        slowmode_enabled=True,
        linked_monoforum_id=None,
        migrated_to=None,
        participants_count=12,
    )
    profile = min_profile_from_entity(entity)
    assert profile["title"] == "News"
    assert profile["username"] == "news"
    assert profile["verified"] is True
    assert profile["noforwards"] is True
    assert profile["has_link"] is True
    assert profile["slowmode_enabled"] is True
    assert profile["participants_count"] == 12


def test_user_names_become_title() -> None:
    entity = SimpleNamespace(
        title=None,
        first_name="Ada",
        last_name="Lovelace",
        username=None,
        usernames=None,
    )
    profile = min_profile_from_entity(entity)
    assert profile["title"] == "Ada Lovelace"
    assert profile["first_name"] == "Ada"
    assert profile["last_name"] == "Lovelace"


def test_full_profile_signs_linked_channel() -> None:
    raw = 555
    full = SimpleNamespace(
        full_chat=SimpleNamespace(
            about="bio",
            participants_count=100,
            linked_chat_id=raw,
            migrated_from_chat_id=88,
            slowmode_seconds=30,
            hidden_prehistory=True,
            available_min_id=4,
            participants_hidden=False,
            admins_count=3,
            kicked_count=1,
            banned_count=2,
            online_count=9,
            ttl_period=None,
            pinned_msg_id=12,
            common_chats_count=None,
            location=SimpleNamespace(
                address="Kyiv",
                geo_point=SimpleNamespace(lat=50.45, long=30.52),
            ),
        )
    )
    entity = SimpleNamespace(id=1)
    fields = full_profile_from_full(full, entity=entity)
    assert fields["about"] == "bio"
    assert fields["linked_chat_id"] == signed_peer_id_from_raw_channel_id(raw)
    assert fields["migrated_from_chat_id"] == -88
    assert fields["slowmode_seconds"] == 30
    assert fields["hidden_prehistory"] is True
    assert fields["location_address"] == "Kyiv"
    assert fields["location_lat"] == 50.45
    assert fields["location_lng"] == 30.52


def test_restriction_reason_csv() -> None:
    assert (
        restriction_reason_csv(
            [{"platform": "ios", "reason": "porn", "text": "blocked"}]
        )
        == "ios:porn: blocked"
    )
