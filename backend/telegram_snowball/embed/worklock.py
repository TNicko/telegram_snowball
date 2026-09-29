"""Serialize download + encode on the embed sidecar process."""

from __future__ import annotations

import asyncio

_lock: asyncio.Lock | None = None


def inference_lock() -> asyncio.Lock:
    global _lock
    if _lock is None:
        _lock = asyncio.Lock()
    return _lock
