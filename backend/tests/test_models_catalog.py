from __future__ import annotations

from pathlib import Path

from telegram_snowball.config import Settings
from telegram_snowball.models_catalog import (
    default_selection,
    load_selection,
    mark_model_ready,
    model_is_ready,
    models_for_slot,
    save_selection,
)
from telegram_snowball.models_health import models_catalog_payload, models_health


def _settings(tmp_path: Path) -> Settings:
    return Settings(snowball_data_dir=tmp_path, postgres_dsn="postgresql://unused")


def test_defaults_prefer_local_sizes() -> None:
    selected = default_selection()
    assert selected["image"] == "siglip2-base-patch16-256"
    assert selected["text"] == "multilingual-e5-small"
    assert selected["caption"] == "none"


def test_slot_options_are_smallest_first() -> None:
    assert [item["id"] for item in models_for_slot("image")] == [
        "clip-vit-base-patch32",
        "siglip2-base-patch16-256",
        "siglip2-so400m-patch16-256",
        "mobilenet-v3-large",
    ]
    assert [item["id"] for item in models_for_slot("text")] == [
        "bge-small-en-v1.5",
        "multilingual-e5-small",
        "bge-m3",
    ]
    assert [item["id"] for item in models_for_slot("caption")] == [
        "none",
        "blip-image-captioning-base",
    ]


def test_none_caption_is_ready(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    assert model_is_ready(settings, "none")
    health = models_health(settings)
    assert health["caption"]["ready"] is True
    assert health["image"]["ready"] is False
    assert health["text"]["ready"] is False


def test_selection_and_ready_marker(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    save_selection(settings, {"text": "bge-m3"})
    assert load_selection(settings)["text"] == "bge-m3"
    mark_model_ready(settings, "bge-m3")
    health = models_health(settings)
    assert health["text"]["id"] == "bge-m3"
    assert health["text"]["ready"] is True
    payload = models_catalog_payload(settings)
    assert payload["catalog"]["text"]
    assert any(item["id"] == "bge-m3" and item["selected"] for item in payload["catalog"]["text"])
    assert "note" not in payload
    vision = next(item for item in payload["catalog"]["image"] if item["id"] == "siglip2-base-patch16-256")
    assert vision["recommended"] is True
    assert vision["default"] is True
    assert vision["group"] == "multimodal"
    assert vision["group_label"] == "Vision-language"
    assert vision["multimodal"] is True
    quality = next(item for item in payload["catalog"]["image"] if item["id"] == "siglip2-so400m-patch16-256")
    assert quality["recommended"] is False
    assert sum(1 for item in payload["catalog"]["image"] if item["recommended"]) == 1
    assert "Select the image embedding model" in payload["copy"]["image"]["blurb"]
    mobile = next(item for item in payload["catalog"]["image"] if item["id"] == "mobilenet-v3-large")
    assert mobile["group"] == "image_only"
    assert mobile["group_label"] == "Image-only"
    assert mobile["recommended"] is False
    assert mobile["multimodal"] is False


def test_rejects_wrong_slot(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    try:
        save_selection(settings, {"image": "bge-m3"})
    except ValueError as exc:
        assert "image" in str(exc)
    else:
        raise AssertionError("expected slot mismatch")
