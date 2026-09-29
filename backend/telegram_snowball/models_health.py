"""Local embedding-model health.

v1 snowball jobs default embed_images/embed_text to True. The API refuses to
queue those jobs unless the matching *selected* model is marked ready. Markers
live under ``data/models/<id>/READY``.
"""

from __future__ import annotations

from typing import Any

from telegram_snowball.config import Settings
from telegram_snowball.models_catalog import (
    SLOT_COPY,
    SLOTS,
    catalog_by_id,
    load_selection,
    model_is_ready,
    models_for_slot,
    public_spec,
)


def models_health(settings: Settings) -> dict[str, Any]:
    selected = load_selection(settings)
    slots: dict[str, Any] = {}
    for slot in SLOTS:
        spec = catalog_by_id(selected[slot])
        slots[slot] = public_spec(spec, settings=settings, selected_id=selected[slot])
        slots[slot]["title"] = SLOT_COPY[slot]["title"]
    return slots


def models_catalog_payload(settings: Settings) -> dict[str, Any]:
    selected = load_selection(settings)
    catalog: dict[str, list[dict[str, Any]]] = {}
    for slot in SLOTS:
        items = list(models_for_slot(slot))
        selected_id = selected[slot]
        if selected_id and not any(item["id"] == selected_id for item in items):
            try:
                extra = catalog_by_id(selected_id)
            except KeyError:
                extra = None
            if extra and extra["slot"] == slot:
                items.insert(0, extra)
        catalog[slot] = [
            public_spec(item, settings=settings, selected_id=selected_id) for item in items
        ]
    return {
        "slots": models_health(settings),
        "catalog": catalog,
        "copy": SLOT_COPY,
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
