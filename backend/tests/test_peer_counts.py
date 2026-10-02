from telegram_snowball.peer_counts import message_insert_deltas, stats_from_counts


def test_stats_from_counts_fills_missing_columns() -> None:
    stats = stats_from_counts({"posts": 4, "text_total": "2", "peer_external_id": 9})
    assert stats["posts"] == 4
    assert stats["text_total"] == 2
    assert stats["image_unique"] == 0
    assert "peer_external_id" not in stats


def test_stats_from_counts_empty_row() -> None:
    stats = stats_from_counts(None)
    assert stats["posts"] == 0
    assert stats["total_forwards"] == 0


def test_message_insert_deltas_counts_text_and_downloaded_image() -> None:
    assert message_insert_deltas(content="  hello ", kind="image", downloaded=True) == {
        "posts": 1,
        "text_total": 1,
        "image_total": 1,
        "image_downloaded": 1,
    }


def test_message_insert_deltas_ignores_blank_text_and_unknown_kind() -> None:
    assert message_insert_deltas(content="  ", kind="sticker", downloaded=True) == {"posts": 1}
