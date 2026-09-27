"""Load selected local Hugging Face models and encode text / images."""

from __future__ import annotations

import logging
from io import BytesIO
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from telegram_snowball.config import Settings
from telegram_snowball.models_catalog import catalog_by_id, load_selection, model_dir, model_is_ready

lg = logging.getLogger(__name__)

_CACHE: dict[str, "LoadedEncoder"] = {}


class EncoderError(RuntimeError):
    pass


def vision_is_multimodal(model_id: str) -> bool:
    try:
        spec = catalog_by_id(model_id)
    except KeyError:
        return False
    return str(spec.get("group") or "") == "multimodal"


def _require_transformers() -> None:
    try:
        import transformers  # noqa: F401
        import torch  # noqa: F401
    except ImportError as exc:
        raise EncoderError(
            "Embedding runtime is not installed. Rebuild the Docker image so the "
            "worker has torch + transformers."
        ) from exc


def _device() -> Any:
    import torch

    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


def _as_pil(data: bytes) -> Image.Image:
    img = Image.open(BytesIO(data))
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    elif img.mode == "L":
        img = img.convert("RGB")
    return img


def _mean_pool(last_hidden: Any, attention_mask: Any) -> Any:
    import torch

    mask = attention_mask.unsqueeze(-1).expand(last_hidden.size()).to(last_hidden.dtype)
    summed = (last_hidden * mask).sum(dim=1)
    counts = mask.sum(dim=1).clamp(min=1e-9)
    return summed / counts


def prefix_texts(model_id: str, texts: list[str], *, is_query: bool) -> list[str]:
    if model_id == "multilingual-e5-small":
        tag = "query" if is_query else "passage"
        return [f"{tag}: {text}" for text in texts]
    if model_id == "bge-small-en-v1.5" and is_query:
        return [
            f"Represent this sentence for searching relevant passages: {text}" for text in texts
        ]
    return list(texts)


class LoadedEncoder:
    def __init__(self, model_id: str, slot: str, path: Path) -> None:
        _require_transformers()
        import torch
        from transformers import AutoImageProcessor, AutoModel, AutoProcessor, AutoTokenizer

        self.model_id = model_id
        self.slot = slot
        self.path = path
        self.device = _device()
        self.multimodal = vision_is_multimodal(model_id) if slot == "image" else False
        loc = str(path)
        lg.info("loading embedding model %s from %s on %s", model_id, loc, self.device)
        if slot == "text":
            self.tokenizer = AutoTokenizer.from_pretrained(loc, local_files_only=True)
            self.model = AutoModel.from_pretrained(loc, local_files_only=True)
            self.processor = None
        else:
            self.tokenizer = None
            try:
                self.processor = AutoProcessor.from_pretrained(loc, local_files_only=True)
            except Exception:
                self.processor = AutoImageProcessor.from_pretrained(loc, local_files_only=True)
            self.model = AutoModel.from_pretrained(loc, local_files_only=True)
        self.model.to(self.device)
        self.model.eval()
        self._torch = torch

    def encode_texts(self, texts: list[str], *, is_query: bool = False) -> list[np.ndarray]:
        if not texts:
            return []
        torch = self._torch
        prefixed = prefix_texts(self.model_id, texts, is_query=is_query)
        if self.slot == "image":
            if not self.multimodal:
                raise EncoderError(
                    f"{self.model_id} is image-only. It cannot embed text queries."
                )
            if self.processor is None:
                raise EncoderError("vision processor missing")
            with torch.inference_mode():
                inputs = self.processor(
                    text=prefixed,
                    return_tensors="pt",
                    padding=True,
                    truncation=True,
                )
                inputs = {key: value.to(self.device) for key, value in inputs.items()}
                if hasattr(self.model, "get_text_features"):
                    feats = self.model.get_text_features(**inputs)
                else:
                    out = self.model(**inputs)
                    feats = out.pooler_output if getattr(out, "pooler_output", None) is not None else out.last_hidden_state[:, 0]
        else:
            if self.tokenizer is None:
                raise EncoderError("text tokenizer missing")
            with torch.inference_mode():
                inputs = self.tokenizer(
                    prefixed,
                    return_tensors="pt",
                    padding=True,
                    truncation=True,
                    max_length=512,
                )
                inputs = {key: value.to(self.device) for key, value in inputs.items()}
                out = self.model(**inputs)
                if self.model_id.startswith("bge-") and getattr(out, "pooler_output", None) is not None:
                    feats = out.pooler_output
                else:
                    feats = _mean_pool(out.last_hidden_state, inputs["attention_mask"])
        cpu = feats.detach().float().cpu().numpy()
        return [cpu[i] for i in range(cpu.shape[0])]

    def encode_images(self, payloads: list[bytes]) -> list[np.ndarray]:
        if not payloads:
            return []
        if self.slot != "image":
            raise EncoderError("text models cannot encode images")
        if self.processor is None:
            raise EncoderError("vision processor missing")
        torch = self._torch
        images = [_as_pil(item) for item in payloads]
        with torch.inference_mode():
            try:
                inputs = self.processor(images=images, return_tensors="pt")
            except TypeError:
                inputs = self.processor(images, return_tensors="pt")
            inputs = {key: value.to(self.device) for key, value in inputs.items() if hasattr(value, "to")}
            if hasattr(self.model, "get_image_features"):
                feats = self.model.get_image_features(**inputs)
            else:
                out = self.model(**inputs, output_hidden_states=True)
                hidden = getattr(out, "last_hidden_state", None)
                if hidden is None and getattr(out, "hidden_states", None):
                    hidden = out.hidden_states[-1]
                if hidden is None:
                    raise EncoderError(f"{self.model_id} did not return image features")
                if hidden.ndim == 4:
                    feats = hidden.mean(dim=(2, 3))
                elif hidden.ndim == 3:
                    feats = hidden.mean(dim=1)
                else:
                    feats = hidden
        cpu = feats.detach().float().cpu().numpy()
        return [cpu[i] for i in range(cpu.shape[0])]


def load_encoder(settings: Settings, slot: str) -> LoadedEncoder:
    selected = load_selection(settings)
    model_id = selected[slot]  # type: ignore[index]
    if slot == "caption":
        raise EncoderError("captioning is not an embedding slot")
    if not model_is_ready(settings, model_id):
        spec = catalog_by_id(model_id)
        raise EncoderError(f"{spec['label']} is not ready. Download it from Home → Models.")
    cached = _CACHE.get(model_id)
    if cached is not None:
        return cached
    path = model_dir(settings, model_id)
    loaded = LoadedEncoder(model_id, slot, path)
    _CACHE[model_id] = loaded
    return loaded


def drop_cached(model_id: str | None = None) -> None:
    if model_id is None:
        _CACHE.clear()
        return
    _CACHE.pop(model_id, None)
