from __future__ import annotations

from typing import Any

from telegram_snowball.catalog import attach_catalog_stats, load_catalog_stats
from telegram_snowball.export.files import (
    download_response,
    export_stamp,
    write_csv,
    write_json,
    write_zip,
)
from telegram_snowball.telegram.profile import restriction_reason_csv, usernames_csv

PEER_TYPES = ("channel", "megagroup", "chat", "user", "bot")
TYPE_CSV_NAME = {
    "channel": "channels.csv",
    "megagroup": "megagroups.csv",
    "chat": "chats.csv",
    "user": "users.csv",
    "bot": "bots.csv",
}

PEER_CSV_COLUMNS = [
    "external_id",
    "peer_type",
    "title",
    "first_name",
    "last_name",
    "username",
    "usernames",
    "about",
    "telegram_date",
    "created_at",
    "updated_at",
    "last_message_at",
    "participants_count",
    "posts",
    "forwards_unique",
    "forwards_total",
    "images_unique",
    "images_persisted",
    "videos_total",
    "videos_downloaded",
    "audio_total",
    "gif_total",
    "document_total",
    "verified",
    "scam",
    "fake",
    "restricted",
    "restriction_reason",
    "noforwards",
    "forum",
    "gigagroup",
    "join_to_send",
    "join_request",
    "has_link",
    "has_geo",
    "deleted",
    "premium",
    "deactivated",
    "slowmode_enabled",
    "slowmode_seconds",
    "hidden_prehistory",
    "available_min_id",
    "participants_hidden",
    "admins_count",
    "kicked_count",
    "banned_count",
    "online_count",
    "ttl_period",
    "pinned_msg_id",
    "linked_chat_id",
    "linked_monoforum_id",
    "migrated_from_chat_id",
    "migrated_to_channel_id",
    "location_address",
    "location_lat",
    "location_lng",
    "common_chats_count",
    "has_fetch_coverage",
    "embed_text",
    "embed_images",
    "videos_excluded",
    "large_excluded",
    "max_media_bytes",
]

PEER_SELECT = """
    external_id, peer_type, title, first_name, last_name, username, usernames, about,
    telegram_date, created_at, updated_at, last_message_at, last_message_id,
    participants_count, messages_scraped,
    verified, scam, fake, restricted, restriction_reason, noforwards, forum, gigagroup,
    join_to_send, join_request, has_link, has_geo, deleted, premium, deactivated,
    slowmode_enabled, slowmode_seconds, hidden_prehistory, available_min_id,
    participants_hidden, admins_count, kicked_count, banned_count, online_count,
    ttl_period, pinned_msg_id, linked_chat_id, linked_monoforum_id,
    migrated_from_chat_id, migrated_to_channel_id, location_address, location_lat,
    location_lng, common_chats_count
"""

FORWARD_CSV_COLUMNS = [
    "from_external_id",
    "from_peer_type",
    "from_title",
    "from_username",
    "to_external_id",
    "to_peer_type",
    "to_title",
    "to_username",
    "last_from_name",
    "forward_count",
    "first_seen_at",
    "last_seen_at",
]


def _media_bucket(peer: dict[str, Any], kind: str, field: str) -> int | None:
    media = peer.get("media")
    if not isinstance(media, dict):
        return None
    bucket = media.get(kind)
    if not isinstance(bucket, dict):
        return None
    value = bucket.get(field)
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _embed_ratio(peer: dict[str, Any], key: str) -> str | None:
    bucket = peer.get(key)
    if not isinstance(bucket, dict):
        return None
    try:
        done = int(bucket.get("done"))
        total = int(bucket.get("total"))
    except (TypeError, ValueError):
        return None
    return f"{done}/{total}"


def flatten_peer_csv(peer: dict[str, Any]) -> dict[str, Any]:
    row = {key: peer.get(key) for key in PEER_CSV_COLUMNS}
    row["usernames"] = usernames_csv(peer.get("usernames"))
    row["restriction_reason"] = restriction_reason_csv(peer.get("restriction_reason"))
    row["images_unique"] = _media_bucket(peer, "image", "unique")
    if row["images_unique"] is None:
        row["images_unique"] = _media_bucket(peer, "image", "total")
    row["images_persisted"] = _media_bucket(peer, "image", "downloaded")
    row["videos_total"] = _media_bucket(peer, "video", "total")
    row["videos_downloaded"] = _media_bucket(peer, "video", "downloaded")
    row["audio_total"] = _media_bucket(peer, "audio", "total")
    row["gif_total"] = _media_bucket(peer, "gif", "total")
    row["document_total"] = _media_bucket(peer, "document", "total")
    row["embed_text"] = _embed_ratio(peer, "embed_text")
    row["embed_images"] = _embed_ratio(peer, "embed_images")
    return row


def json_peer(peer: dict[str, Any]) -> dict[str, Any]:
    skip = {"photo_path", "photo_url", "photo_media_kind", "access_hash", "is_scraping", "scrape_detail"}
    return {key: value for key, value in peer.items() if key not in skip}


def normalize_peer_types(peer_types: list[str] | None) -> list[str]:
    if not peer_types:
        return list(PEER_TYPES)
    allowed = set(PEER_TYPES)
    out = [item for item in peer_types if item in allowed]
    return out or list(PEER_TYPES)


async def load_export_peers(conn: Any, peer_types: list[str]) -> list[dict[str, Any]]:
    rows = await conn.execute(
        f"""
        SELECT {PEER_SELECT}
        FROM peers
        WHERE peer_type = ANY(%s)
        ORDER BY created_at DESC, external_id DESC
        """,
        (peer_types,),
    )
    items = [dict(row) for row in await rows.fetchall()]
    fetch_ids, media_cov, message_stats = await load_catalog_stats(conn)
    return [
        attach_catalog_stats(peer, fetch_ids=fetch_ids, media_cov=media_cov, message_stats=message_stats)
        for peer in items
    ]


async def load_forward_edges(conn: Any, peer_ids: list[int]) -> list[dict[str, Any]]:
    if not peer_ids:
        return []
    rows = await conn.execute(
        """
        SELECT
            e.from_external_id, e.to_external_id, e.from_peer_type, e.to_peer_type,
            e.last_from_name, e.forward_count, e.first_seen_at, e.last_seen_at,
            fp.title AS from_title, fp.username AS from_username,
            tp.title AS to_title, tp.username AS to_username
        FROM forward_edges e
        LEFT JOIN peers fp ON fp.external_id = e.from_external_id
        LEFT JOIN peers tp ON tp.external_id = e.to_external_id
        WHERE e.from_external_id = ANY(%s)
        ORDER BY e.forward_count DESC, e.from_external_id, e.to_external_id
        """,
        (peer_ids,),
    )
    return [dict(row) for row in await rows.fetchall()]


async def export_peers(
    conn: Any,
    *,
    fmt: str,
    peer_types: list[str] | None,
    include_forward_edges: bool,
):
    types = normalize_peer_types(peer_types)
    peers = await load_export_peers(conn, types)
    stamp = export_stamp()
    grouped: dict[str, list[dict[str, Any]]] = {kind: [] for kind in types}
    for peer in peers:
        kind = str(peer.get("peer_type") or "")
        grouped.setdefault(kind, []).append(peer)
    edge_ids = [int(peer["external_id"]) for peer in peers]
    edges = await load_forward_edges(conn, edge_ids) if include_forward_edges else []

    if fmt == "json":
        payload: dict[str, Any] = {
            "exported_at": stamp,
            "filters": {"peer_types": types, "include_forward_edges": include_forward_edges},
            "counts": {kind: len(grouped.get(kind, [])) for kind in types},
            "peers": {kind: [json_peer(peer) for peer in grouped.get(kind, [])] for kind in types},
        }
        if include_forward_edges:
            payload["forward_edges"] = edges
        return download_response(
            write_json(payload),
            filename=f"snowball-general-{stamp}.json",
            media_type="application/json",
        )

    files: dict[str, bytes] = {}
    for kind in types:
        rows = [flatten_peer_csv(peer) for peer in grouped.get(kind, [])]
        if not rows:
            continue
        name = TYPE_CSV_NAME.get(kind, f"{kind}.csv")
        files[name] = write_csv(rows, PEER_CSV_COLUMNS)
    if include_forward_edges and edges:
        files["forward_edges.csv"] = write_csv(edges, FORWARD_CSV_COLUMNS)
    if not files:
        files["channels.csv"] = write_csv([], PEER_CSV_COLUMNS)
    return download_response(
        write_zip(files),
        filename=f"snowball-general-{stamp}.zip",
        media_type="application/zip",
    )
