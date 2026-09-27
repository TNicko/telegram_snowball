from __future__ import annotations

from telegram_snowball.api.routes.graph import build_message_layer, origin_keys_from_forward_rows
from telegram_snowball.telegram.ids import signed_peer_id_from_raw_channel_id


def test_build_message_layer_one_node_sent_to_and_forwarded_from() -> None:
    origin_peer = signed_peer_id_from_raw_channel_id(99)
    rows = [
        {
            "id": "11111111-1111-1111-1111-111111111111",
            "peer_external_id": -100,
            "telegram_message_id": 7,
            "date": "2026-01-02T00:00:00+00:00",
            "excerpt": "hello",
            "media_kind": "image",
            "fwd_from": {
                "from_id": {"_": "PeerChannel", "channel_id": 99},
                "channel_post": 44,
            },
        }
    ]
    nodes, edges = build_message_layer(rows, {})
    assert len(nodes) == 1
    node = nodes[0]
    stub_id = f"m:orig:{origin_peer}:44"
    assert node["id"] == stub_id
    assert node["stub"] is True
    assert node["message_id"] == "11111111-1111-1111-1111-111111111111"
    assert node["peer_external_id"] == origin_peer
    assert node["telegram_message_id"] == 44
    kinds = {(edge["kind"], edge["source"], edge["target"]) for edge in edges}
    assert ("sent_to", stub_id, str(origin_peer)) in kinds
    assert ("forwarded_from", "-100", stub_id) in kinds
    assert origin_keys_from_forward_rows(rows) == [(origin_peer, 44)]


def test_build_message_layer_reuses_stored_original() -> None:
    origin_peer = signed_peer_id_from_raw_channel_id(5)
    forward_id = "22222222-2222-2222-2222-222222222222"
    origin_id = "33333333-3333-3333-3333-333333333333"
    rows = [
        {
            "id": forward_id,
            "peer_external_id": -200,
            "telegram_message_id": 9,
            "date": "2026-03-01T00:00:00+00:00",
            "excerpt": None,
            "media_kind": None,
            "fwd_from": {
                "from_id": {"_": "PeerChannel", "channel_id": 5},
                "channel_post": 3,
            },
        }
    ]
    origin = {
        "id": origin_id,
        "peer_external_id": origin_peer,
        "telegram_message_id": 3,
        "date": "2025-12-01T00:00:00+00:00",
        "excerpt": "source",
        "media_kind": "video",
        "forwarded": False,
    }
    nodes, edges = build_message_layer(rows, {(origin_peer, 3): origin})
    assert len(nodes) == 1
    node = nodes[0]
    assert node["id"] == f"m:{origin_id}"
    assert node["stub"] is False
    assert node["message_id"] == origin_id
    assert node["date"] == "2025-12-01T00:00:00+00:00"
    assert node["excerpt"] == "source"
    assert node["media_kind"] == "video"
    kinds = {(edge["kind"], edge["source"], edge["target"]) for edge in edges}
    assert ("sent_to", f"m:{origin_id}", str(origin_peer)) in kinds
    assert ("forwarded_from", "-200", f"m:{origin_id}") in kinds
    assert f"m:{forward_id}" not in {item["id"] for item in nodes}


def test_build_message_layer_collapses_repeat_forwards() -> None:
    origin_peer = signed_peer_id_from_raw_channel_id(8)
    rows = [
        {
            "id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            "peer_external_id": -10,
            "telegram_message_id": 1,
            "date": "2026-04-02T00:00:00+00:00",
            "excerpt": "later copy",
            "media_kind": None,
            "fwd_from": {
                "from_id": {"_": "PeerChannel", "channel_id": 8},
                "channel_post": 12,
            },
        },
        {
            "id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
            "peer_external_id": -20,
            "telegram_message_id": 2,
            "date": "2026-04-01T00:00:00+00:00",
            "excerpt": "earlier copy",
            "media_kind": "gif",
            "fwd_from": {
                "from_id": {"_": "PeerChannel", "channel_id": 8},
                "channel_post": 12,
            },
        },
    ]
    nodes, edges = build_message_layer(rows, {})
    assert len(nodes) == 1
    node = nodes[0]
    stub_id = f"m:orig:{origin_peer}:12"
    assert node["id"] == stub_id
    assert node["date"] == "2026-04-01T00:00:00+00:00"
    assert node["excerpt"] == "later copy"
    assert node["media_kind"] == "gif"
    assert node["message_id"] == "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
    kinds = {(edge["kind"], edge["source"], edge["target"]) for edge in edges}
    assert ("sent_to", stub_id, str(origin_peer)) in kinds
    assert ("forwarded_from", "-10", stub_id) in kinds
    assert ("forwarded_from", "-20", stub_id) in kinds
    assert len(edges) == 3


def test_build_message_layer_skips_forwards_without_origin() -> None:
    rows = [
        {
            "id": "cccccccc-cccc-cccc-cccc-cccccccccccc",
            "peer_external_id": -100,
            "telegram_message_id": 7,
            "date": "2026-01-02T00:00:00+00:00",
            "excerpt": "hello",
            "media_kind": "image",
            "fwd_from": {"from_id": {"_": "PeerChannel", "channel_id": 99}},
        }
    ]
    nodes, edges = build_message_layer(rows, {})
    assert nodes == []
    assert edges == []
