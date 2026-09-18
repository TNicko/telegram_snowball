from __future__ import annotations

from typing import Any

from telethon import utils

CHANNEL_MARK = 1_000_000_000_000


def to_signed_peer_id(peer: Any) -> int | None:
    if peer is None:
        return None
    return int(utils.get_peer_id(peer))


def infer_peer_id_kind(value: str) -> str | None:
    """Return 'peer_id' if the string looks like a signed Telegram peer id."""
    raw = value.strip()
    if not raw:
        return None
    if raw.startswith("@"):
        return None
    try:
        signed = int(raw)
    except ValueError:
        return None
    if signed > 0:
        return "peer_id"
    if -signed > CHANNEL_MARK:
        return "peer_id"
    if signed < 0:
        return "peer_id"
    return None


def peer_type_for_entity(entity: Any) -> str:
    from telethon.tl.types import Channel, Chat, User

    if isinstance(entity, User):
        return "bot" if bool(getattr(entity, "bot", False)) else "user"
    if isinstance(entity, Channel):
        return "megagroup" if bool(getattr(entity, "megagroup", False)) else "channel"
    if isinstance(entity, Chat):
        return "chat"
    return "channel"
