from __future__ import annotations

from datetime import datetime, timezone

from telegram_snowball.catalog import attach_catalog_stats, build_peer_coverage, time_coverage_ratio


def _peer(**overrides: object) -> dict:
    row = {
        "external_id": 1,
        "messages_scraped": 0,
    }
    row.update(overrides)
    return row


def test_attach_shows_posts_while_scrape_is_in_progress() -> None:
    peer = attach_catalog_stats(
        _peer(messages_scraped=24),
        fetch_ids=set(),
        media_cov={},
        message_stats={1: {"posts": 24, "image_total": 3, "unique_forwards": 2, "total_forwards": 5}},
    )
    assert peer["posts"] == 24
    assert peer["forwards_unique"] == 2
    assert peer["forwards_total"] == 5
    assert peer["media"]["image"] == {"total": 3, "hashed": 0, "downloaded": 0, "unique": 0}


def test_attach_falls_back_to_messages_scraped() -> None:
    peer = attach_catalog_stats(
        _peer(messages_scraped=12),
        fetch_ids=set(),
        media_cov={},
        message_stats={},
    )
    assert peer["posts"] == 12


def test_attach_keeps_dash_until_any_posts_exist() -> None:
    peer = attach_catalog_stats(
        _peer(),
        fetch_ids=set(),
        media_cov={},
        message_stats={},
    )
    assert peer["posts"] is None
    assert peer["forwards_unique"] is None
    assert peer["embed_text"] is None
    assert peer["embed_images"] is None


def test_attach_embed_progress_after_scrape() -> None:
    peer = attach_catalog_stats(
        _peer(),
        fetch_ids={1},
        media_cov={},
        message_stats={
            1: {
                "posts": 12,
                "text_total": 10,
                "text_embedded": 4,
                "image_embeddable": 6,
                "image_embedded_unique": 2,
            }
        },
    )
    assert peer["embed_text"] == {"done": 4, "total": 10}
    assert peer["embed_images"] == {"done": 2, "total": 6}


def test_time_coverage_ratio_walks_back_from_now() -> None:
    origin = datetime(2024, 6, 1, tzinfo=timezone.utc)
    now = datetime(2026, 6, 1, tzinfo=timezone.utc)
    assert time_coverage_ratio(origin, now, datetime(2025, 6, 1, tzinfo=timezone.utc)) == 0.5
    assert time_coverage_ratio(origin, now, origin) == 1.0
    assert time_coverage_ratio(origin, now, None) == 0.0
    assert time_coverage_ratio(None, now, origin) == 0.0


def test_build_peer_coverage_windows() -> None:
    now = datetime(2026, 9, 25, 12, 0, tzinfo=timezone.utc)
    body = build_peer_coverage(
        _peer(title="News", first_message_id=1, first_message_at="2021-03-12T00:00:00+00:00"),
        fetch={
            "covered_after": "2021-03-12T00:00:00+00:00",
            "covered_before": "2026-09-25T12:00:00+00:00",
            "updated_at": "2026-09-25T12:00:00+00:00",
        },
        media={
            "covered_after": "2021-03-12T00:00:00+00:00",
            "covered_before": "2026-09-25T12:00:00+00:00",
            "videos_excluded": True,
            "large_excluded": False,
            "max_media_bytes": None,
            "updated_at": "2026-09-25T12:00:00+00:00",
        },
        stats={
            "posts": 40,
            "text_total": 10,
            "text_embedded": 8,
            "text_embed_after": "2021-03-12T00:00:00+00:00",
            "image_unique": 12,
            "image_persisted": 5,
            "image_total": 12,
            "image_hashed": 8,
            "image_embedded": 4,
            "image_after": "2024-01-01T00:00:00+00:00",
            "unique_forwards": 3,
            "total_forwards": 7,
        },
        now=now,
    )
    assert body["posts"]["count"] == 40
    assert body["posts"]["covered_after"] == "2021-03-12T00:00:00+00:00"
    assert body["posts"]["covered_before"] == "2026-09-25T12:00:00+00:00"
    assert body["posts"]["fill"] == 1.0
    assert body["timeline"]["start"] == "2021-03-12T00:00:00+00:00"
    assert body["timeline"]["end"] == now.isoformat()
    assert body["media_pass"]["videos_excluded"] is True
    assert body["embeds"]["text"]["total"] == 10
    assert body["embeds"]["text"]["done"] == 8
    assert body["embeds"]["text"]["fill"] == 1.0
    assert body["embeds"]["images"]["fill"] == 0.0
    assert body["media_layers"]["image"]["fill"] > 0
    assert body["media_layers"]["image"]["fill"] < 1
    assert body["forwards"]["fill"] == 1.0
    assert body["peer"]["media"]["image"] == {
        "total": 12,
        "hashed": 8,
        "downloaded": 5,
        "unique": 12,
    }


def test_build_peer_coverage_without_windows() -> None:
    body = build_peer_coverage(_peer(), fetch=None, media=None, stats=None)
    assert body["posts"]["count"] is None
    assert body["posts"]["covered_after"] is None
    assert body["posts"]["fill"] == 0.0
    assert body["timeline"]["start"] is None
    assert body["media_pass"] is None
    assert body["peer"]["embed_text"] is None
    assert body["peer"]["embed_images"] is None
    assert body["embeds"]["text"] == {
        "total": 0,
        "done": 0,
        "covered_after": None,
        "covered_before": None,
        "fill": 0.0,
    }


def test_build_peer_coverage_empty_scrape_shows_zero_posts() -> None:
    body = build_peer_coverage(
        _peer(),
        fetch={
            "covered_after": "2026-09-25T12:00:00+00:00",
            "covered_before": "2026-09-25T12:00:00+00:00",
        },
        media=None,
        stats={"posts": 0},
    )
    assert body["posts"]["count"] == 0
    assert body["peer"]["embed_text"] is None
    assert body["peer"]["embed_images"] is None


def test_build_peer_coverage_uses_first_message_origin() -> None:
    now = datetime(2026, 6, 1, tzinfo=timezone.utc)
    body = build_peer_coverage(
        _peer(first_message_id=1, first_message_at="2024-06-01T00:00:00+00:00"),
        fetch={
            "covered_after": "2025-06-01T00:00:00+00:00",
            "covered_before": "2026-06-01T00:00:00+00:00",
        },
        media=None,
        stats={"posts": 10},
        now=now,
    )
    assert body["timeline"]["start"] == "2024-06-01T00:00:00+00:00"
    assert body["posts"]["fill"] == 0.5


def test_build_peer_coverage_timeline_uses_first_message_not_window() -> None:
    now = datetime(2026, 9, 25, 12, 0, tzinfo=timezone.utc)
    body = build_peer_coverage(
        _peer(),
        fetch={
            "covered_after": "2026-04-07T00:00:00+00:00",
            "covered_before": "2026-09-25T12:00:00+00:00",
        },
        media=None,
        stats={"posts": 10, "unique_forwards": 4, "total_forwards": 6},
        now=now,
    )
    assert body["timeline"]["start"] is None
    assert body["posts"]["covered_after"] == "2026-04-07T00:00:00+00:00"
    assert body["posts"]["fill"] == 0.0
