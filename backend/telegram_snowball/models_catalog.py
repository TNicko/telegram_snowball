"""Local embedding-model catalog.

Vision models (CLIP / SigLIP) encode images *and* text into one space, which is
what multimodal search needs. MobileNet is an image-only CNN in the same vision
slot: visual similarity, no text-to-image. Message-text models (E5 / BGE) are a
separate space for message-to-message similarity. Mixing those two spaces is not
a search. Captions are optional: they turn an image into words, then the text
model can search those words. They are not required if a vision model is ready.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from telegram_snowball.config import Settings

Slot = Literal["image", "text", "caption"]

SELECTED_FILENAME = "selected.json"

# Conservative disk / memory figures for users picking a local model.
MODELS: list[dict[str, Any]] = [
    {
        "id": "clip-vit-base-patch32",
        "slot": "image",
        "label": "CLIP ViT-B/32",
        "hf_id": "openai/clip-vit-base-patch32",
        "license": "MIT",
        "default": False,
        "download_gb": 0.6,
        "ram_gb": 3,
        "vram_gb": 1.5,
        "hardware": "Laptop CPU, 8 GB RAM",
        "purpose": "Smaller and faster. Weaker on screenshots, memes, and non-English text in images.",
        "group": "multimodal",
        "group_label": "Vision-language",
    },
    {
        "id": "siglip2-base-patch16-256",
        "slot": "image",
        "label": "SigLIP2 Base",
        "hf_id": "google/siglip2-base-patch16-256",
        "license": "Apache-2.0",
        "default": True,
        "download_gb": 1.1,
        "ram_gb": 5,
        "vram_gb": 2,
        "hardware": "8 GB RAM, or any 4 GB GPU",
        "purpose": "Similar photos and text-to-image search. Fits an 8 GB laptop.",
        "recommended": True,
        "group": "multimodal",
        "group_label": "Vision-language",
    },
    {
        "id": "siglip2-so400m-patch16-256",
        "slot": "image",
        "label": "SigLIP2 So400m",
        "hf_id": "google/siglip2-so400m-patch16-256",
        "license": "Apache-2.0",
        "default": False,
        "download_gb": 3.4,
        "ram_gb": 10,
        "vram_gb": 6,
        "hardware": "16 GB RAM, or an 8 GB GPU",
        "purpose": "Stronger on screenshots, memes, and text in images. Better for a large Telegram catalog.",
        "group": "multimodal",
        "group_label": "Vision-language",
    },
    {
        "id": "mobilenet-v3-large",
        "slot": "image",
        "label": "MobileNet V3 Large",
        "hf_id": "google/mobilenet_v3_large_100_224",
        "license": "Apache-2.0",
        "default": False,
        "download_gb": 0.03,
        "ram_gb": 1,
        "vram_gb": 0.5,
        "hardware": "Any machine",
        "purpose": "Tiny and fast image-to-image matching. No text-to-image — it has no language encoder.",
        "group": "image_only",
        "group_label": "Image-only",
    },
    {
        "id": "bge-small-en-v1.5",
        "slot": "text",
        "label": "BGE Small English",
        "hf_id": "BAAI/bge-small-en-v1.5",
        "license": "MIT",
        "default": False,
        "download_gb": 0.13,
        "ram_gb": 1,
        "vram_gb": 0.5,
        "hardware": "Any machine",
        "purpose": "Tiny and fast. English-only message text.",
    },
    {
        "id": "multilingual-e5-small",
        "slot": "text",
        "label": "E5 Small multilingual",
        "hf_id": "intfloat/multilingual-e5-small",
        "license": "MIT",
        "default": True,
        "download_gb": 0.5,
        "ram_gb": 2,
        "vram_gb": 1,
        "hardware": "Laptop CPU, 8 GB RAM",
        "purpose": "Default message-to-message search. Covers the languages Telegram actually uses.",
    },
    {
        "id": "bge-m3",
        "slot": "text",
        "label": "BGE-M3",
        "hf_id": "BAAI/bge-m3",
        "license": "MIT",
        "default": False,
        "download_gb": 2.3,
        "ram_gb": 8,
        "vram_gb": 3,
        "hardware": "16 GB RAM, or a 6 GB GPU",
        "purpose": "Highest quality message matching, including long posts. Heavy as a default.",
    },
    {
        "id": "none",
        "slot": "caption",
        "label": "No captions",
        "hf_id": None,
        "license": None,
        "default": True,
        "download_gb": 0,
        "ram_gb": 0,
        "vram_gb": 0,
        "hardware": "",
        "purpose": "",
    },
    {
        "id": "blip-image-captioning-base",
        "slot": "caption",
        "label": "BLIP Base",
        "hf_id": "Salesforce/blip-image-captioning-base",
        "license": "BSD-3-Clause",
        "default": False,
        "download_gb": 1.0,
        "ram_gb": 4,
        "vram_gb": 2,
        "hardware": "8 GB RAM, or a 4 GB GPU",
        "purpose": "",
    },
]

SLOTS: tuple[Slot, ...] = ("image", "text", "caption")

# Vision: CLIP / SigLIP first (smallest to largest), then image-only alternatives.
_GROUP_RANK = {"multimodal": 0, "image_only": 1}
_GROUP_LABELS = {"multimodal": "Vision-language", "image_only": "Image-only"}

SLOT_COPY: dict[Slot, dict[str, str]] = {
    "image": {
        "title": "Vision",
        "blurb": (
            "Select the image embedding model based on your use case and hardware. "
            "SigLIP2 Base is recommended for most users."
        ),
    },
    "text": {
        "title": "Message text",
        "blurb": (
            "A separate space for message-to-message meaning. "
            "It cannot be compared to vision vectors."
        ),
    },
    "caption": {
        "title": "Captions",
        "blurb": "Select a captioning model based on your use case and hardware.",
    },
}


def catalog_by_id(model_id: str) -> dict[str, Any]:
    for item in MODELS:
        if item["id"] == model_id:
            return item
    raise KeyError(model_id)


def models_for_slot(slot: Slot) -> list[dict[str, Any]]:
    return sorted(
        (item for item in MODELS if item["slot"] == slot),
        key=lambda item: (
            _GROUP_RANK.get(str(item.get("group") or ""), 0),
            float(item["download_gb"]),
            float(item["ram_gb"]),
            item["id"],
        ),
    )


def default_id_for_slot(slot: Slot) -> str:
    for item in models_for_slot(slot):
        if item.get("default"):
            return str(item["id"])
    raise KeyError(slot)


def default_selection() -> dict[Slot, str]:
    return {slot: default_id_for_slot(slot) for slot in SLOTS}


def selected_path(settings: Settings) -> Path:
    return settings.data_dir / "models" / SELECTED_FILENAME


def load_selection(settings: Settings) -> dict[Slot, str]:
    selected = default_selection()
    path = selected_path(settings)
    if not path.is_file():
        return selected
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return selected
    if not isinstance(raw, dict):
        return selected
    for slot in SLOTS:
        value = raw.get(slot)
        if not isinstance(value, str):
            continue
        try:
            spec = catalog_by_id(value)
        except KeyError:
            continue
        if spec["slot"] == slot:
            selected[slot] = value
    return selected


def save_selection(settings: Settings, patch: dict[str, str]) -> dict[Slot, str]:
    selected = load_selection(settings)
    for slot in SLOTS:
        value = patch.get(slot)
        if not value:
            continue
        spec = catalog_by_id(value)
        if spec["slot"] != slot:
            raise ValueError(f"{value} is not a {slot} model")
        selected[slot] = value
    dest = selected_path(settings)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(selected, indent=2) + "\n", encoding="utf-8")
    return selected


def model_dir(settings: Settings, model_id: str) -> Path:
    return settings.data_dir / "models" / model_id


def ready_file(settings: Settings, model_id: str) -> Path:
    return model_dir(settings, model_id) / "READY"


def model_has_weights(settings: Settings, model_id: str) -> bool:
    root = model_dir(settings, model_id)
    if not root.is_dir() or not (root / "config.json").is_file():
        return False
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() in {".safetensors", ".bin"} and path.stat().st_size > 0:
            return True
    return False


def model_is_ready(settings: Settings, model_id: str) -> bool:
    if model_id == "none":
        return True
    return ready_file(settings, model_id).is_file() and model_has_weights(settings, model_id)


def mark_model_ready(settings: Settings, model_id: str) -> None:
    dest = ready_file(settings, model_id)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("ok\n", encoding="utf-8")
    if not model_has_weights(settings, model_id):
        (dest.parent / "config.json").write_text("{}\n", encoding="utf-8")
        (dest.parent / "model.safetensors").write_bytes(b"stub")


def public_spec(item: dict[str, Any], *, settings: Settings, selected_id: str | None = None) -> dict[str, Any]:
    model_id = str(item["id"])
    return {
        "id": model_id,
        "slot": item["slot"],
        "label": item["label"],
        "license": item["license"],
        "default": bool(item.get("default")),
        "download_gb": item["download_gb"],
        "ram_gb": item["ram_gb"],
        "vram_gb": item["vram_gb"],
        "hardware": item["hardware"],
        "purpose": item["purpose"],
        "recommended": bool(item.get("recommended")),
        "group": item.get("group"),
        "group_label": item.get("group_label")
        or _GROUP_LABELS.get(str(item.get("group") or ""))
        or None,
        "multimodal": str(item.get("group") or "") == "multimodal",
        "ready": model_is_ready(settings, model_id),
        "selected": selected_id == model_id,
    }
