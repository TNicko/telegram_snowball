"""64-bit perceptual hash for raster images."""

from __future__ import annotations

from io import BytesIO

PHASH_BITS = 64
ZERO_PHASH = "0000000000000000"


def int_to_hex(value: int) -> str:
    return f"{value & ((1 << PHASH_BITS) - 1):016x}"


def normalize_phash_hex(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if len(normalized) != 16 or any(ch not in "0123456789abcdef" for ch in normalized):
        return None
    return normalized


def is_dedupable_phash(value: str | None) -> bool:
    normalized = normalize_phash_hex(value)
    return normalized is not None and normalized != ZERO_PHASH


def compute_phash(image_bytes: bytes) -> int:
    from PIL import Image
    import imagehash

    with Image.open(BytesIO(image_bytes)) as img:
        digest = imagehash.phash(img)
    return int(str(digest), 16)


def phash_hex_from_bytes(image_bytes: bytes) -> str:
    return int_to_hex(compute_phash(image_bytes))
