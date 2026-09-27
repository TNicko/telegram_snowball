from __future__ import annotations

from io import BytesIO

from PIL import Image

from telegram_snowball.phash import (
    ZERO_PHASH,
    is_dedupable_phash,
    normalize_phash_hex,
    phash_hex_from_bytes,
)
from telegram_snowball.telegram.image_files import cache_rel_path, canonical_rel_path


def _png(color: tuple[int, int, int]) -> bytes:
    buf = BytesIO()
    Image.new("RGB", (48, 48), color).save(buf, format="PNG")
    return buf.getvalue()


def test_normalize_phash_hex() -> None:
    assert normalize_phash_hex(" 0123456789ABCDEF ") == "0123456789abcdef"
    assert normalize_phash_hex("dead") is None
    assert normalize_phash_hex("gggggggggggggggg") is None


def test_zero_phash_is_not_dedupable() -> None:
    assert not is_dedupable_phash(ZERO_PHASH)
    assert not is_dedupable_phash(None)
    assert is_dedupable_phash("0123456789abcdef")


def test_identical_images_share_phash() -> None:
    first = phash_hex_from_bytes(_png((12, 80, 160)))
    second = phash_hex_from_bytes(_png((12, 80, 160)))
    assert first == second
    assert is_dedupable_phash(first)
    assert len(first) == 16


def test_different_images_usually_differ() -> None:
    dark = phash_hex_from_bytes(_png((0, 0, 0)))
    bright = phash_hex_from_bytes(_png((255, 255, 255)))
    assert dark != bright


def test_canonical_rel_path() -> None:
    assert canonical_rel_path("0123456789abcdef", ".jpg") == "blobs/images/01/0123456789abcdef.jpg"
    assert canonical_rel_path("abcdef0123456789", "PNG") == "blobs/images/ab/abcdef0123456789.png"


def test_cache_rel_path() -> None:
    assert cache_rel_path("0123456789abcdef", ".jpg") == "cache/images/01/0123456789abcdef.jpg"
    assert cache_rel_path("abcdef0123456789", "webp") == "cache/images/ab/abcdef0123456789.webp"
