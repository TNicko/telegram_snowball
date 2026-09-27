from __future__ import annotations

import numpy as np
import pytest

from telegram_snowball.embed.runtime import prefix_texts
from telegram_snowball.embed.vectors import VECTOR_WIDTH, pad_unit, vector_literal


def test_pad_unit_preserves_cosine() -> None:
    a = np.array([3.0, 4.0], dtype=np.float32)
    b = np.array([6.0, 8.0], dtype=np.float32)
    pa = pad_unit(a)
    pb = pad_unit(b)
    assert pa.shape == (VECTOR_WIDTH,)
    cosine = float(np.dot(pa, pb))
    assert cosine == pytest.approx(1.0, abs=1e-5)


def test_pad_rejects_oversize() -> None:
    with pytest.raises(ValueError, match="exceeds"):
        pad_unit(np.ones(VECTOR_WIDTH + 1, dtype=np.float32))


def test_vector_literal_format() -> None:
    lit = vector_literal([1.0, 0.0])
    assert lit.startswith("[")
    assert lit.endswith("]")
    assert lit.count(",") == VECTOR_WIDTH - 1


def test_e5_prefixes() -> None:
    assert prefix_texts("multilingual-e5-small", ["hello"], is_query=True) == ["query: hello"]
    assert prefix_texts("multilingual-e5-small", ["hello"], is_query=False) == ["passage: hello"]


def test_bge_query_prefix() -> None:
    out = prefix_texts("bge-small-en-v1.5", ["hello"], is_query=True)
    assert out[0].startswith("Represent this sentence")
    assert prefix_texts("bge-small-en-v1.5", ["hello"], is_query=False) == ["hello"]
