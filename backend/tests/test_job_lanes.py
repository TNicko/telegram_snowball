from __future__ import annotations

import pytest

from telegram_snowball.jobs import runners_for
from telegram_snowball.jobs.lanes import (
    EMBED_TASKS,
    SCRAPE_TASKS,
    lane_for,
    live_conflict_detail,
    tasks_for_kind,
)


def test_lane_split() -> None:
    assert lane_for("fetch_dialogues") == "scrape"
    assert lane_for("forward_snowball") == "scrape"
    assert lane_for("download_model") == "embed"
    assert lane_for("embed") == "embed"
    assert "embed" not in SCRAPE_TASKS
    assert "forward_snowball" not in EMBED_TASKS
    assert lane_for("scope_rerank") == "embed"


def test_kind_task_lists() -> None:
    assert tasks_for_kind("scrape") == SCRAPE_TASKS
    assert tasks_for_kind("embed") == EMBED_TASKS
    assert tasks_for_kind("other") == SCRAPE_TASKS


def test_conflict_copy() -> None:
    assert "session" in live_conflict_detail("scrape")
    assert "download" in live_conflict_detail("embed").lower()


def test_unknown_task_raises() -> None:
    with pytest.raises(ValueError, match="Unknown task_type"):
        lane_for("not_a_task")


def test_runners_for_kind() -> None:
    assert set(runners_for("scrape")) == {"fetch_dialogues", "forward_snowball"}
    assert set(runners_for("embed")) == {"download_model", "embed", "scope_rerank"}
