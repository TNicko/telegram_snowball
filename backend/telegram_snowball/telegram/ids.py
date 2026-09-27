from __future__ import annotations

from typing import Any

from telethon import utils
from telethon.tl.types import (
    Channel,
    ChannelForbidden,
    Chat,
    ChatForbidden,
    InputPeerChannel,
    InputPeerChat,
    InputPeerUser,
    User,
)

CHANNEL_MARK = 1_000_000_000_000


def to_signed_peer_id(peer: Any) -> int | None:
    if peer is None:
        return None
    try:
        return int(utils.get_peer_id(peer))
    except Exception:
        return None


def channel_id_from_signed_peer_id(signed_peer_id: int) -> int | None:
    if signed_peer_id >= 0:
        return None
    marked = -signed_peer_id
    if marked <= CHANNEL_MARK:
        return None
    return marked - CHANNEL_MARK


def signed_peer_id_from_raw_channel_id(raw_channel_id: int) -> int:
    return -(CHANNEL_MARK + int(raw_channel_id))


def infer_peer_type_from_signed(signed_peer_id: int) -> str:
    if channel_id_from_signed_peer_id(signed_peer_id) is not None:
        return "channel"
    if signed_peer_id < 0:
        return "chat"
    return "user"


def is_snowball_target(signed_peer_id: int) -> bool:
    """Forward-graph scrape targets: channels, megagroups, and basic chats — not users."""
    return signed_peer_id < 0


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
    if isinstance(entity, User):
        return "bot" if bool(getattr(entity, "bot", False)) else "user"
    if isinstance(entity, (Channel, ChannelForbidden)):
        return "megagroup" if bool(getattr(entity, "megagroup", False)) else "channel"
    if isinstance(entity, (Chat, ChatForbidden)):
        return "chat"
    return infer_peer_type_from_signed(to_signed_peer_id(entity) or 0)


def input_peer_from_stored(
    *,
    external_id: int,
    peer_type: str | None,
    access_hash: int | None,
) -> InputPeerChannel | InputPeerChat | InputPeerUser | None:
    """Build an InputPeer from a catalog row so StringSession can fetch without cache."""
    kind = peer_type or infer_peer_type_from_signed(external_id)
    if kind in ("channel", "megagroup"):
        raw = channel_id_from_signed_peer_id(external_id)
        if raw is None or access_hash is None:
            return None
        return InputPeerChannel(raw, int(access_hash))
    if kind == "chat":
        chat_id = -external_id if external_id < 0 else external_id
        return InputPeerChat(int(chat_id))
    if kind in ("user", "bot") and access_hash is not None and external_id > 0:
        return InputPeerUser(int(external_id), int(access_hash))
    return None
