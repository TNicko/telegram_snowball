from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from telegram_snowball.scope.score import (
    ScopeParams,
    as_unit_vector,
    forward_score,
    max_cosine,
    mix_score,
    pick_frontier_index,
    relevance_r,
)


def test_relevance_zeros_at_and_below_tau() -> None:
    params = ScopeParams(tau=0.4, gamma=2.0)
    assert relevance_r(0.22, params) == 0.0
    assert relevance_r(0.4, params) == 0.0
    assert relevance_r(0.399, params) == 0.0


def test_relevance_at_one_is_one() -> None:
    params = ScopeParams(tau=0.4, gamma=2.0)
    assert relevance_r(1.0, params) == pytest.approx(1.0)


def test_relevance_mid_band() -> None:
    params = ScopeParams(tau=0.4, gamma=2.0)
    # s=0.7 → ((0.3)/0.6)^2 = 0.25
    assert relevance_r(0.7, params) == pytest.approx(0.25)
    assert relevance_r(0.5, params) == pytest.approx((0.1 / 0.6) ** 2)


def test_mix_and_forward_formula() -> None:
    params = ScopeParams(alpha=2.0, delta=0.15, lambda_fwd=0.05)
    mix = mix_score(1.0, 4, params)
    assert mix == pytest.approx(1.0 / (1.0 + 2.0 + 0.15 * 4))
    fwd = forward_score(mix, 3, params)
    assert fwd == pytest.approx(mix + 0.05 * np.log1p(3))


def test_max_cosine_picks_best_input() -> None:
    image = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    inputs = np.array(
        [
            [0.2, 0.98, 0.0],
            [0.9, 0.1, 0.0],
        ],
        dtype=np.float32,
    )
    # not unit, so normalize via pad_unit through as_unit_vector
    image_u = as_unit_vector(image, width=3)
    inputs_u = np.stack([as_unit_vector(row, width=3) for row in inputs])
    assert max_cosine(image_u, inputs_u) == pytest.approx(float(np.dot(inputs_u[1], image_u)))


def test_as_unit_vector_parses_pg_text() -> None:
    raw = as_unit_vector("[3.0,4.0,0.0]", width=5)
    assert raw.shape == (5,)
    assert float(np.linalg.norm(raw)) == pytest.approx(1.0)
    assert raw[2:].sum() == 0


def test_frontier_keeps_seed_then_heap() -> None:
    seed = SimpleNamespace(peer_id=1, depth=0, retry=False)
    a = SimpleNamespace(peer_id=2, depth=1, retry=False)
    b = SimpleNamespace(peer_id=3, depth=1, retry=False)
    items = [seed, a, b]
    assert pick_frontier_index(items, {2: 0.9, 3: 0.1}, use_scope=True) == 0
    rest = [a, b]
    assert pick_frontier_index(rest, {2: 0.2, 3: 0.8}, use_scope=True) == 1
    assert pick_frontier_index(rest, {2: 0.2, 3: 0.8}, use_scope=False) == 0


def test_frontier_retry_beats_score() -> None:
    retry = SimpleNamespace(peer_id=9, depth=1, retry=True)
    hot = SimpleNamespace(peer_id=8, depth=1, retry=False)
    items = [hot, retry]
    assert pick_frontier_index(items, {8: 9.0, 9: 0.0}, use_scope=True) == 1
