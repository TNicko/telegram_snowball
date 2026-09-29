"""Vision-space Scope scoring.

Cosine ``s`` is similarity (1 = identical). Images at or below ``tau`` get
relevance 0. Peer mix is ``R / (R + alpha + delta * J)``. Forward score adds
``lambda * log(1 + events)``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from telegram_snowball.embed.vectors import VECTOR_WIDTH, pad_unit

DEFAULT_TAU = 0.4
DEFAULT_GAMMA = 2.0
DEFAULT_ALPHA = 2.0
DEFAULT_DELTA = 0.15
DEFAULT_LAMBDA = 0.05


@dataclass(frozen=True, slots=True)
class ScopeParams:
    tau: float = DEFAULT_TAU
    gamma: float = DEFAULT_GAMMA
    alpha: float = DEFAULT_ALPHA
    delta: float = DEFAULT_DELTA
    lambda_fwd: float = DEFAULT_LAMBDA
    version: int = 0


def as_unit_vector(raw: Any, *, width: int = VECTOR_WIDTH) -> np.ndarray:
    if isinstance(raw, np.ndarray):
        values = raw.astype(np.float32, copy=False).reshape(-1)
    elif isinstance(raw, (list, tuple)):
        values = np.asarray(raw, dtype=np.float32).reshape(-1)
    else:
        to_list = getattr(raw, "tolist", None)
        if callable(to_list):
            values = np.asarray(to_list(), dtype=np.float32).reshape(-1)
        else:
            text = str(raw).strip()
            if text.startswith("[") and text.endswith("]"):
                text = text[1:-1]
            values = np.asarray(
                [float(part) for part in text.split(",") if part.strip()],
                dtype=np.float32,
            )
    return pad_unit(values, width)


def relevance_r(s: float, params: ScopeParams | None = None) -> float:
    cfg = params or ScopeParams()
    if s <= cfg.tau:
        return 0.0
    span = 1.0 - cfg.tau
    if span <= 0:
        return 1.0 if s > cfg.tau else 0.0
    return float(((s - cfg.tau) / span) ** cfg.gamma)


def mix_score(r_sum: float, unique_n: int, params: ScopeParams | None = None) -> float:
    cfg = params or ScopeParams()
    denom = r_sum + cfg.alpha + cfg.delta * unique_n
    if denom <= 0:
        return 0.0
    return float(r_sum / denom)


def forward_score(mix: float, events: int, params: ScopeParams | None = None) -> float:
    cfg = params or ScopeParams()
    if events < 0:
        events = 0
    return float(mix + cfg.lambda_fwd * np.log1p(events))


def max_cosine(image: np.ndarray, inputs: np.ndarray) -> float:
    """Max cosine of one image against K input rows (both unit, same width)."""
    if inputs.size == 0:
        return 0.0
    if inputs.ndim == 1:
        inputs = inputs.reshape(1, -1)
    dots = inputs @ image.reshape(-1)
    return float(np.max(dots))


def score_image(image: np.ndarray, inputs: np.ndarray, params: ScopeParams | None = None) -> tuple[float, float]:
    s = max_cosine(image, inputs)
    return s, relevance_r(s, params)


def pick_frontier_index(
    items: list[Any],
    scores: dict[int, float],
    *,
    use_scope: bool,
) -> int:
    """Choose the next frontier item.

    Retry (FloodWait) and the unfinished seed (depth 0) stay FIFO. After the
    seed, Scope picks the pending peer with the highest ``forward_score``.
    """
    if not items:
        raise IndexError("empty frontier")
    for i, item in enumerate(items):
        if getattr(item, "retry", False):
            return i
    for i, item in enumerate(items):
        if int(getattr(item, "depth", 0) or 0) == 0:
            return i
    if not use_scope:
        return 0
    best_i = 0
    best_key: tuple[float, int] | None = None
    for i, item in enumerate(items):
        peer_id = int(item.peer_id)
        key = (float(scores.get(peer_id, 0.0)), peer_id)
        if best_key is None or key > best_key:
            best_key = key
            best_i = i
    return best_i
