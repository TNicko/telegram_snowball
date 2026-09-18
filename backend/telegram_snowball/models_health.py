"""Local embedding-model health.

v1 snowball jobs default embed_images/embed_text to True. The API refuses to
queue those jobs unless the matching model is marked ready. Markers live under
``data/models/<name>/READY``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from telegram_snowball.config import Settings

IMAGE_MODEL_ID = "siglip2-base-patch16-256"
TEXT_MODEL_ID = "bge-m3"
CAPTION_MODEL_ID = "blip-image-captioning-base"


def _ready_file(settings: Settings, name: str) -> Path:
    return settings.data_dir / "models" / name / "READY"


def model_ready(settings: Settings, name: str) -> bool:
    return _ready_file(settings, name).is_file()


def models_health(settings: Settings) -> dict[str, Any]:
    image = model_ready(settings, IMAGE_MODEL_ID)
    text = model_ready(settings, TEXT_MODEL_ID)
    caption = model_ready(settings, CAPTION_MODEL_ID)
    return {
        "image": {
            "id": IMAGE_MODEL_ID,
            "ready": image,
            "label": "SigLIP2 (images)",
        },
        "text": {
            "id": TEXT_MODEL_ID,
            "ready": text,
            "label": "BGE-M3 (message text)",
        },
        "caption": {
            "id": CAPTION_MODEL_ID,
            "ready": caption,
            "label": "BLIP (image captions)",
        },
    }


class EmbeddingGateError(ValueError):
    pass


def assert_snowball_embed_gate(settings: Settings, params: dict[str, Any]) -> None:
    """Reject a snowball job when a requested embedder is not healthy."""
    embed_images = bool(params.get("embed_images", True))
    embed_text = bool(params.get("embed_text", True))
    health = models_health(settings)
    missing: list[str] = []
    if embed_images and not health["image"]["ready"]:
        missing.append(health["image"]["label"])
    if embed_text and not health["text"]["ready"]:
        missing.append(health["text"]["label"])
    if missing:
        names = ", ".join(missing)
        raise EmbeddingGateError(
            f"Cannot start snowball: embedding is on but not ready ({names}). "
            "Turn off image/text embedding in the job config, or finish model setup."
        )
