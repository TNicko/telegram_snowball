"""Extract catalog identity + PeerFull fields from Telethon min / full objects."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from telegram_snowball.telegram.ids import signed_peer_id_from_raw_channel_id


def _attr(obj: Any, name: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _bool(obj: Any, name: str) -> bool | None:
    value = _attr(obj, name)
    if value is None:
        return None
    return bool(value)


def _int(obj: Any, name: str) -> int | None:
    value = _attr(obj, name)
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float(obj: Any, name: str) -> float | None:
    value = _attr(obj, name)
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _str(obj: Any, name: str) -> str | None:
    value = _attr(obj, name)
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _dt(obj: Any, name: str) -> datetime | None:
    value = _attr(obj, name)
    if isinstance(value, datetime):
        return value
    return None


def _canonical_username(value: str) -> str:
    return value.strip().lstrip("@")


def usernames_from_entity(entity: Any) -> list[dict[str, Any]]:
    """Primary handle first, then Channel/User ``usernames`` (incl. inactive)."""
    out: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(username: str | None, *, active: bool | None, editable: bool | None) -> None:
        if not username:
            return
        handle = _canonical_username(username)
        if not handle:
            return
        key = handle.lower()
        if key in seen:
            return
        seen.add(key)
        row: dict[str, Any] = {"username": handle}
        if active is not None:
            row["active"] = bool(active)
        if editable is not None:
            row["editable"] = bool(editable)
        out.append(row)

    extra = _attr(entity, "usernames") or []
    if isinstance(extra, list):
        for entry in extra:
            add(
                _str(entry, "username"),
                active=_bool(entry, "active"),
                editable=_bool(entry, "editable"),
            )
    add(_str(entity, "username"), active=True, editable=None)
    primary = _str(entity, "username")
    if primary:
        handle = _canonical_username(primary)
        rest = [row for row in out if row["username"].lower() != handle.lower()]
        head = next((row for row in out if row["username"].lower() == handle.lower()), None)
        if head is not None:
            if "active" not in head:
                head["active"] = True
            out = [head, *rest]
    return out


def restriction_reason_from_entity(entity: Any) -> list[dict[str, str]] | None:
    raw = _attr(entity, "restriction_reason")
    if raw is None:
        return None
    if not isinstance(raw, list):
        return []
    out: list[dict[str, str]] = []
    for entry in raw:
        platform = _str(entry, "platform") or ""
        reason = _str(entry, "reason") or ""
        text = _str(entry, "text") or ""
        if platform or reason or text:
            out.append({"platform": platform, "reason": reason, "text": text})
    return out


def _signed_channel_id(raw: int | None) -> int | None:
    if raw is None:
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    if value <= 0:
        return None
    return signed_peer_id_from_raw_channel_id(value)


def _signed_chat_id(raw: int | None) -> int | None:
    if raw is None:
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    if value == 0:
        return None
    return -abs(value)


def display_title(entity: Any) -> str | None:
    title = _str(entity, "title")
    if title:
        return title
    first = _str(entity, "first_name")
    last = _str(entity, "last_name")
    joined = " ".join(part for part in (first, last) if part)
    return joined or None


def min_profile_from_entity(entity: Any) -> dict[str, Any]:
    """Fields available on Channel / Chat / User (and Forbidden variants)."""
    usernames = usernames_from_entity(entity)
    migrated_to = _attr(entity, "migrated_to")
    linked_monoforum = _int(entity, "linked_monoforum_id")
    return {
        "title": display_title(entity),
        "first_name": _str(entity, "first_name"),
        "last_name": _str(entity, "last_name"),
        "username": _str(entity, "username"),
        "usernames": usernames or None,
        "telegram_date": _dt(entity, "date"),
        "verified": _bool(entity, "verified"),
        "scam": _bool(entity, "scam"),
        "fake": _bool(entity, "fake"),
        "restricted": _bool(entity, "restricted"),
        "restriction_reason": restriction_reason_from_entity(entity),
        "noforwards": _bool(entity, "noforwards"),
        "forum": _bool(entity, "forum"),
        "gigagroup": _bool(entity, "gigagroup"),
        "join_to_send": _bool(entity, "join_to_send"),
        "join_request": _bool(entity, "join_request"),
        "has_link": _bool(entity, "has_link"),
        "has_geo": _bool(entity, "has_geo"),
        "deleted": _bool(entity, "deleted"),
        "premium": _bool(entity, "premium"),
        "deactivated": _bool(entity, "deactivated"),
        "slowmode_enabled": _bool(entity, "slowmode_enabled"),
        "linked_monoforum_id": _signed_channel_id(linked_monoforum),
        "migrated_to_channel_id": _signed_channel_id(_int(migrated_to, "channel_id")),
        "participants_count": _int(entity, "participants_count"),
    }


def _location_fields(location: Any) -> dict[str, Any]:
    if location is None:
        return {}
    geo = _attr(location, "geo_point")
    lat = _float(geo, "lat")
    lng = _float(geo, "long")
    if lng is None:
        lng = _float(geo, "lng")
    return {
        "location_address": _str(location, "address"),
        "location_lat": lat,
        "location_lng": lng,
    }


def full_profile_from_full(full: Any, *, entity: Any | None = None) -> dict[str, Any]:
    """Fields from messages.ChatFull / users.UserFull wrappers or the inner Full object."""
    if full is None:
        return {}
    inner = _attr(full, "full_chat")
    if inner is None:
        inner = _attr(full, "full_user")
    if inner is None:
        inner = full
    linked_raw = _int(inner, "linked_chat_id")
    parent_raw = _int(entity, "id") if entity is not None else None
    linked_signed = _signed_channel_id(linked_raw)
    if parent_raw is not None and linked_raw == parent_raw:
        linked_signed = None
    out: dict[str, Any] = {
        "about": _str(inner, "about"),
        "participants_count": _int(inner, "participants_count"),
        "linked_chat_id": linked_signed,
        "migrated_from_chat_id": _signed_chat_id(_int(inner, "migrated_from_chat_id")),
        "slowmode_seconds": _int(inner, "slowmode_seconds"),
        "hidden_prehistory": _bool(inner, "hidden_prehistory"),
        "available_min_id": _int(inner, "available_min_id"),
        "participants_hidden": _bool(inner, "participants_hidden"),
        "admins_count": _int(inner, "admins_count"),
        "kicked_count": _int(inner, "kicked_count"),
        "banned_count": _int(inner, "banned_count"),
        "online_count": _int(inner, "online_count"),
        "ttl_period": _int(inner, "ttl_period"),
        "pinned_msg_id": _int(inner, "pinned_msg_id"),
        "common_chats_count": _int(inner, "common_chats_count"),
    }
    out.update(_location_fields(_attr(inner, "location")))
    return {key: value for key, value in out.items() if value is not None}


def usernames_csv(usernames: Any) -> str:
    if not isinstance(usernames, list):
        return ""
    handles: list[str] = []
    seen: set[str] = set()
    for entry in usernames:
        handle = None
        if isinstance(entry, str):
            handle = _canonical_username(entry)
        elif isinstance(entry, dict):
            raw = entry.get("username")
            if isinstance(raw, str):
                handle = _canonical_username(raw)
        if handle and handle.lower() not in seen:
            seen.add(handle.lower())
            handles.append(handle)
    return ";".join(handles)


def restriction_reason_csv(value: Any) -> str:
    if not isinstance(value, list):
        return ""
    parts: list[str] = []
    for entry in value:
        if not isinstance(entry, dict):
            continue
        platform = str(entry.get("platform") or "").strip()
        reason = str(entry.get("reason") or "").strip()
        text = str(entry.get("text") or "").strip()
        chunk = ":".join(part for part in (platform, reason) if part)
        if text and text not in chunk:
            chunk = f"{chunk}: {text}" if chunk else text
        if chunk:
            parts.append(chunk)
    return "; ".join(parts)
