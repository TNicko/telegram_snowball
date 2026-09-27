from __future__ import annotations

from pathlib import Path

import pytest

from telegram_snowball.config import Settings
from telegram_snowball.models_catalog import mark_model_ready
from telegram_snowball.models_health import EmbeddingGateError, assert_snowball_embed_gate


def _settings(tmp_path: Path) -> Settings:
    return Settings(snowball_data_dir=tmp_path, postgres_dsn="postgresql://unused")


def test_default_embed_flags_require_models(tmp_path: Path) -> None:
    with pytest.raises(EmbeddingGateError, match="embedding is on but not ready"):
        assert_snowball_embed_gate(_settings(tmp_path), {})


def test_images_only_requires_vision_model(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    mark_model_ready(settings, "multilingual-e5-small")
    with pytest.raises(EmbeddingGateError, match="SigLIP"):
        assert_snowball_embed_gate(settings, {"embed_images": True, "embed_text": False})
    assert_snowball_embed_gate(settings, {"embed_images": False, "embed_text": True})


def test_both_off_skips_gate(tmp_path: Path) -> None:
    assert_snowball_embed_gate(
        _settings(tmp_path),
        {"embed_images": False, "embed_text": False},
    )
