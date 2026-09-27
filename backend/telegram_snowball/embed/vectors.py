"""Fixed-width unit vectors for pgvector cosine search."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

VECTOR_WIDTH = 1280


def pad_unit(values: Sequence[float] | np.ndarray, width: int = VECTOR_WIDTH) -> np.ndarray:
    """L2-normalize ``values`` and zero-pad to ``width``.

    Zero-padding after normalization keeps cosine identical to the unpadded
    vector (dots and norms ignore the extra zeros).
    """
    raw = np.asarray(values, dtype=np.float32).reshape(-1)
    if raw.size == 0:
        raise ValueError("empty embedding")
    if raw.size > width:
        raise ValueError(f"embedding dim {raw.size} exceeds slot width {width}")
    norm = float(np.linalg.norm(raw))
    if norm <= 0:
        raise ValueError("zero embedding")
    unit = raw / np.float32(norm)
    if unit.size == width:
        return unit
    out = np.zeros(width, dtype=np.float32)
    out[: unit.size] = unit
    return out


def vector_literal(values: Sequence[float] | np.ndarray, width: int = VECTOR_WIDTH) -> str:
    padded = pad_unit(values, width)
    return "[" + ",".join(f"{float(x):.8f}" for x in padded) + "]"
