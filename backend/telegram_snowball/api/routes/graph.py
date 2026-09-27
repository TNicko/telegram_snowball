from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Query

from telegram_snowball.api.routes.dialogues import PUBLIC_PEER_COLUMNS, public_peer
from telegram_snowball.catalog import _STORED_MEDIA_KIND_SQL
from telegram_snowball.config import load_settings
from telegram_snowball.db import get_conn
from telegram_snowball.telegram.forwards import origin_telegram_id_from_fwd, signed_peer_from_fwd
from telegram_snowball.telegram.ids import channel_id_from_signed_peer_id

router = APIRouter()

MESSAGE_GRAPH_LIMIT = 40_000
IMAGE_GRAPH_LIMIT = 40_000
MIN_SHARED_IMAGE_PEERS = 2
_MEDIA_KINDS = frozenset({"image", "video", "audio", "gif", "document"})
_MEDIA_FILTER_KEYS = ("none", "image", "video", "audio", "gif", "document")
AUTO_NODES = 25_000
AUTO_EDGES = 80_000
AUTO_BYTES = 25 * 1024 * 1024
CONFIRM_NODES = 80_000
CONFIRM_EDGES = 200_000
CONFIRM_BYTES = 80 * 1024 * 1024
_BYTES_PER_PEER = 220
_BYTES_PER_MESSAGE = 420
_BYTES_PER_EDGE = 80


def parse_media_param(media: str | None) -> set[str] | None:
    """None = no filter. Empty set = match nothing."""
    if media is None:
        return None
    parts = {item.strip() for item in media.split(",") if item.strip()}
    if not parts:
        return set()
    valid = {item for item in parts if item in _MEDIA_FILTER_KEYS}
    if not valid:
        return None
    if set(_MEDIA_FILTER_KEYS) <= valid:
        return None
    return valid


def estimate_graph_bytes(peer_count: int, message_count: int, edge_count: int) -> int:
    return (
        max(0, peer_count) * _BYTES_PER_PEER
        + max(0, message_count) * _BYTES_PER_MESSAGE
        + max(0, edge_count) * _BYTES_PER_EDGE
    )


def budget_band(node_count: int, edge_count: int, bytes_estimate: int) -> str:
    if (
        node_count > CONFIRM_NODES
        or edge_count > CONFIRM_EDGES
        or bytes_estimate > CONFIRM_BYTES
    ):
        return "block"
    if node_count > AUTO_NODES or edge_count > AUTO_EDGES or bytes_estimate > AUTO_BYTES:
        return "confirm"
    return "auto"


def fwd_origin_match_sql(peer_id: int, column: str = "m.fwd_from") -> tuple[str, list[Any]]:
    raw_channel = channel_id_from_signed_peer_id(peer_id)
    if raw_channel is not None:
        sql = f"""(
          (
            COALESCE({column}->'from_id'->>'_', {column}->'from_id'->>'tl') = 'PeerChannel'
            AND ({column}->'from_id'->>'channel_id') ~ '^[0-9]+$'
            AND ({column}->'from_id'->>'channel_id')::bigint = %s
          )
          OR (
            COALESCE({column}->'saved_from_peer'->>'_', {column}->'saved_from_peer'->>'tl') = 'PeerChannel'
            AND ({column}->'saved_from_peer'->>'channel_id') ~ '^[0-9]+$'
            AND ({column}->'saved_from_peer'->>'channel_id')::bigint = %s
          )
        )"""
        return sql, [raw_channel, raw_channel]
    if peer_id < 0:
        chat_id = abs(peer_id)
        sql = f"""(
          (
            COALESCE({column}->'from_id'->>'_', {column}->'from_id'->>'tl') = 'PeerChat'
            AND ({column}->'from_id'->>'chat_id') ~ '^[0-9]+$'
            AND ({column}->'from_id'->>'chat_id')::bigint = %s
          )
          OR (
            COALESCE({column}->'saved_from_peer'->>'_', {column}->'saved_from_peer'->>'tl') = 'PeerChat'
            AND ({column}->'saved_from_peer'->>'chat_id') ~ '^[0-9]+$'
            AND ({column}->'saved_from_peer'->>'chat_id')::bigint = %s
          )
        )"""
        return sql, [chat_id, chat_id]
    sql = f"""(
      (
        COALESCE({column}->'from_id'->>'_', {column}->'from_id'->>'tl') = 'PeerUser'
        AND ({column}->'from_id'->>'user_id') ~ '^[0-9]+$'
        AND ({column}->'from_id'->>'user_id')::bigint = %s
      )
      OR (
        COALESCE({column}->'saved_from_peer'->>'_', {column}->'saved_from_peer'->>'tl') = 'PeerUser'
        AND ({column}->'saved_from_peer'->>'user_id') ~ '^[0-9]+$'
        AND ({column}->'saved_from_peer'->>'user_id')::bigint = %s
      )
    )"""
    return sql, [peer_id, peer_id]


def message_filter_sql(
    *,
    peer_id: int | None,
    date_from: datetime | None,
    date_to: datetime | None,
    media: set[str] | None,
) -> tuple[str, list[Any]]:
    clauses: list[str] = ["TRUE"]
    params: list[Any] = []
    if peer_id is not None:
        origin_sql, origin_params = fwd_origin_match_sql(peer_id)
        clauses.append(f"(m.peer_external_id = %s OR {origin_sql})")
        params.append(peer_id)
        params.extend(origin_params)
    if date_from is not None:
        clauses.append("m.date >= %s")
        params.append(date_from)
    if date_to is not None:
        clauses.append("m.date <= %s")
        params.append(date_to)
    if media is not None:
        kind_expr = f"({_STORED_MEDIA_KIND_SQL.strip()})"
        include_none = "none" in media
        typed = sorted(item for item in media if item != "none")
        if not include_none and not typed:
            clauses.append("FALSE")
        elif include_none and typed:
            clauses.append(f"({kind_expr} IS NULL OR {kind_expr} = ANY(%s))")
            params.append(typed)
        elif include_none:
            clauses.append(f"{kind_expr} IS NULL")
        else:
            clauses.append(f"{kind_expr} = ANY(%s)")
            params.append(typed)
    return " AND ".join(clauses), params


def message_scope_is_open(peer_id: int | None, date_from: datetime | None, date_to: datetime | None) -> bool:
    return peer_id is None and date_from is None and date_to is None


def _peer_label(peer: dict[str, Any] | None, fallback: str | None = None) -> str | None:
    if peer:
        title = (peer.get("title") or "").strip()
        if title:
            return title
        username = (peer.get("username") or "").strip()
        if username:
            return f"@{username}"
    if fallback and str(fallback).strip():
        return str(fallback).strip()
    return None


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    text = str(value).strip()
    return text or None


def _media_kind(value: Any) -> str | None:
    kind = str(value).strip() if value is not None else ""
    return kind if kind in _MEDIA_KINDS else None


def _excerpt(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _stored_id(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _message_node(
    *,
    node_id: str,
    peer_id: int,
    telegram_message_id: int | None,
    date: Any,
    excerpt: str | None,
    media_kind: str | None,
    origin_peer_id: int | None = None,
    origin_telegram_id: int | None = None,
    stub: bool = False,
    message_id: str | None = None,
) -> dict[str, Any]:
    label = _excerpt(excerpt)
    return {
        "id": node_id,
        "kind": "message",
        "external_id": peer_id,
        "peer_type": "message",
        "label": label,
        "username": None,
        "photo_url": None,
        "scraped": not stub,
        "is_scraping": False,
        "degree": 0,
        "forward_volume": 0,
        "forwards_unique": 0,
        "forwards_total": 0,
        "forwarded": True,
        "media_kind": media_kind,
        "date": _iso(date),
        "telegram_message_id": telegram_message_id,
        "peer_external_id": peer_id,
        "origin_peer_id": origin_peer_id,
        "origin_telegram_id": origin_telegram_id,
        "excerpt": label,
        "stub": stub,
        "message_id": message_id,
    }


def _fill_stub_content(node: dict[str, Any], row: dict[str, Any]) -> None:
    incoming = _iso(row.get("date"))
    existing = node.get("date")
    if incoming and (not existing or incoming < existing):
        node["date"] = incoming
    text = _excerpt(row.get("excerpt"))
    incoming_kind = _media_kind(row.get("media_kind"))
    stored_id = _stored_id(row.get("id"))
    if stored_id:
        if not node.get("message_id"):
            node["message_id"] = stored_id
        elif (incoming_kind and not node.get("media_kind")) or (text and not node.get("excerpt")):
            node["message_id"] = stored_id
    if text and not node.get("excerpt"):
        node["excerpt"] = text
        node["label"] = text
    if incoming_kind and not node.get("media_kind"):
        node["media_kind"] = incoming_kind


def build_message_layer(
    forward_rows: list[dict[str, Any]],
    origin_by_key: dict[tuple[int, int], dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """One node per original message, with sent_to and forwarded_from peer edges."""
    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []
    seen_edges: set[tuple[str, str, str]] = set()

    def add_edge(kind: str, source: str, target: str, count: int = 1) -> None:
        key = (kind, source, target)
        if source == target or key in seen_edges:
            return
        seen_edges.add(key)
        edges.append({"source": source, "target": target, "count": count, "kind": kind})

    def ensure_origin_node(
        origin_peer: int,
        origin_mid: int,
        forward_row: dict[str, Any],
    ) -> str:
        origin_row = origin_by_key.get((origin_peer, origin_mid))
        if origin_row is not None and origin_row.get("id") is not None:
            node_id = f"m:{origin_row['id']}"
            if node_id not in nodes:
                origin_peer_id = int(origin_row["peer_external_id"])
                origin_telegram = int(origin_row["telegram_message_id"])
                nodes[node_id] = _message_node(
                    node_id=node_id,
                    peer_id=origin_peer_id,
                    telegram_message_id=origin_telegram,
                    date=origin_row.get("date"),
                    excerpt=origin_row.get("excerpt"),
                    media_kind=_media_kind(origin_row.get("media_kind")),
                    origin_peer_id=origin_peer_id,
                    origin_telegram_id=origin_telegram,
                    message_id=_stored_id(origin_row.get("id")),
                )
            return node_id

        node_id = f"m:orig:{origin_peer}:{origin_mid}"
        if node_id not in nodes:
            nodes[node_id] = _message_node(
                node_id=node_id,
                peer_id=origin_peer,
                telegram_message_id=origin_mid,
                date=forward_row.get("date"),
                excerpt=forward_row.get("excerpt"),
                media_kind=_media_kind(forward_row.get("media_kind")),
                origin_peer_id=origin_peer,
                origin_telegram_id=origin_mid,
                stub=True,
                message_id=_stored_id(forward_row.get("id")),
            )
        else:
            _fill_stub_content(nodes[node_id], forward_row)
        return node_id

    for row in forward_rows:
        raw_id = row.get("id")
        if raw_id is None:
            continue
        posting_peer = int(row["peer_external_id"])
        fwd = row.get("fwd_from")
        origin_peer = signed_peer_from_fwd(fwd)
        origin_mid = origin_telegram_id_from_fwd(fwd)

        if origin_peer is None or origin_mid is None:
            continue
        node_id = ensure_origin_node(origin_peer, origin_mid, row)
        add_edge("sent_to", node_id, str(origin_peer))
        add_edge("forwarded_from", str(posting_peer), node_id)

    return list(nodes.values()), edges


def origin_keys_from_forward_rows(forward_rows: list[dict[str, Any]]) -> list[tuple[int, int]]:
    keys: set[tuple[int, int]] = set()
    for row in forward_rows:
        fwd = row.get("fwd_from")
        origin_peer = signed_peer_from_fwd(fwd)
        origin_mid = origin_telegram_id_from_fwd(fwd)
        if origin_peer is None or origin_mid is None:
            continue
        keys.add((origin_peer, origin_mid))
    return sorted(keys)


def _scope_meta(
    *,
    peer_id: int | None,
    date_from: datetime | None,
    date_to: datetime | None,
    media: set[str] | None,
) -> dict[str, Any]:
    return {
        "peer_id": peer_id,
        "date_from": _iso(date_from),
        "date_to": _iso(date_to),
        "media": None if media is None else sorted(media),
        "sample": "newest",
    }


async def _count_message_forwards(conn: Any, where_sql: str, params: list[Any]) -> int:
    found = await conn.execute(
        f"""
        SELECT COUNT(*)::bigint AS n
        FROM forward_edge_messages fem
        JOIN messages m ON m.id = fem.message_id
        WHERE {where_sql}
        """,
        params,
    )
    row = await found.fetchone()
    return int(row["n"] or 0) if row else 0


async def _load_message_rows(
    conn: Any,
    where_sql: str,
    params: list[Any],
) -> tuple[list[dict[str, Any]], dict[tuple[int, int], dict[str, Any]], bool]:
    kind_sql = _STORED_MEDIA_KIND_SQL.strip()
    found_messages = await conn.execute(
        f"""
        SELECT
            m.id,
            m.peer_external_id,
            m.telegram_message_id,
            m.date,
            NULLIF(BTRIM(LEFT(m.content, 80)), '') AS excerpt,
            m.fwd_from,
            ({kind_sql}) AS media_kind
        FROM forward_edge_messages fem
        JOIN messages m ON m.id = fem.message_id
        WHERE {where_sql}
        ORDER BY m.date DESC NULLS LAST
        LIMIT %s
        """,
        (*params, MESSAGE_GRAPH_LIMIT + 1),
    )
    message_rows = [dict(row) for row in await found_messages.fetchall()]
    truncated = len(message_rows) > MESSAGE_GRAPH_LIMIT
    if truncated:
        message_rows = message_rows[:MESSAGE_GRAPH_LIMIT]
    origin_by_key: dict[tuple[int, int], dict[str, Any]] = {}
    keys = origin_keys_from_forward_rows(message_rows)
    if keys:
        origin_found = await conn.execute(
            f"""
            SELECT
                m.id,
                m.peer_external_id,
                m.telegram_message_id,
                m.date,
                NULLIF(BTRIM(LEFT(m.content, 80)), '') AS excerpt,
                ({kind_sql}) AS media_kind,
                (m.fwd_from IS NOT NULL) AS forwarded
            FROM messages m
            WHERE (m.peer_external_id, m.telegram_message_id) IN (
                SELECT * FROM unnest(%s::bigint[], %s::integer[])
            )
            """,
            ([peer for peer, _mid in keys], [mid for _peer, mid in keys]),
        )
        for row in await origin_found.fetchall():
            origin_by_key[(int(row["peer_external_id"]), int(row["telegram_message_id"]))] = dict(row)
    return message_rows, origin_by_key, truncated


@router.get("/graph/forwards/stats")
async def catalog_forward_graph_stats(
    peer_id: int | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    media: str | None = Query(default=None),
) -> dict[str, Any]:
    """Cheap catalog counts so the client can warn before loading messages."""
    settings = load_settings()
    media_kinds = parse_media_param(media)
    where_sql, where_params = message_filter_sql(
        peer_id=peer_id,
        date_from=date_from,
        date_to=date_to,
        media=media_kinds,
    )
    async with get_conn(settings) as conn:
        peer_found = await conn.execute(
            """
            SELECT COUNT(*)::bigint AS n FROM (
              SELECT from_external_id AS id FROM forward_edges
              UNION
              SELECT to_external_id AS id FROM forward_edges
            ) peers
            """
        )
        peer_row = await peer_found.fetchone()
        peer_count = int(peer_row["n"] or 0) if peer_row else 0
        edge_found = await conn.execute("SELECT COUNT(*)::bigint AS n FROM forward_edges")
        edge_row = await edge_found.fetchone()
        peer_edge_count = int(edge_row["n"] or 0) if edge_row else 0
        total_found = await conn.execute("SELECT COUNT(*)::bigint AS n FROM forward_edge_messages")
        total_row = await total_found.fetchone()
        message_forward_count = int(total_row["n"] or 0) if total_row else 0
        scoped_message_count = await _count_message_forwards(conn, where_sql, where_params)

    estimated_message_nodes = scoped_message_count
    estimated_message_edges = scoped_message_count * 2
    estimated_nodes = peer_count + estimated_message_nodes
    estimated_edges = peer_edge_count + estimated_message_edges
    bytes_estimate = estimate_graph_bytes(peer_count, estimated_message_nodes, estimated_edges)
    open_scope = message_scope_is_open(peer_id, date_from, date_to)
    if open_scope:
        band = budget_band(estimated_nodes, estimated_edges, bytes_estimate)
    else:
        capped_nodes = peer_count + min(scoped_message_count, MESSAGE_GRAPH_LIMIT)
        capped_edges = peer_edge_count + min(scoped_message_count, MESSAGE_GRAPH_LIMIT) * 2
        band = budget_band(
            capped_nodes,
            capped_edges,
            estimate_graph_bytes(peer_count, min(scoped_message_count, MESSAGE_GRAPH_LIMIT), capped_edges),
        )
        if band == "block":
            band = "confirm"
    return {
        "peer_count": peer_count,
        "peer_edge_count": peer_edge_count,
        "message_forward_count": message_forward_count,
        "scoped_message_count": scoped_message_count,
        "estimated_nodes": estimated_nodes,
        "estimated_edges": estimated_edges,
        "bytes_estimate": bytes_estimate,
        "band": band,
        "limit": MESSAGE_GRAPH_LIMIT,
        "scope": _scope_meta(
            peer_id=peer_id,
            date_from=date_from,
            date_to=date_to,
            media=media_kinds,
        ),
    }


@router.get("/graph/forwards")
async def catalog_forward_graph(
    messages: bool = Query(default=False),
    peer_id: int | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    media: str | None = Query(default=None),
) -> dict[str, Any]:
    """Entire-catalog community forward graph (unique edges + counts)."""
    settings = load_settings()
    media_kinds = parse_media_param(media)
    where_sql, where_params = message_filter_sql(
        peer_id=peer_id,
        date_from=date_from,
        date_to=date_to,
        media=media_kinds,
    )
    message_rows: list[dict[str, Any]] = []
    origin_by_key: dict[tuple[int, int], dict[str, Any]] = {}
    messages_truncated = False
    messages_omitted = False
    omit_reason: str | None = None
    scoped_message_total = 0
    message_forward_total = 0
    include_messages = messages
    async with get_conn(settings) as conn:
        edge_rows = await conn.execute(
            """
            SELECT
                from_external_id, to_external_id, from_peer_type, to_peer_type,
                last_from_name, forward_count
            FROM forward_edges
            """
        )
        raw_edges = [dict(row) for row in await edge_rows.fetchall()]
        fetch_rows = await conn.execute("SELECT peer_external_id FROM peer_fetch_coverage")
        scraped_ids = {int(row["peer_external_id"]) for row in await fetch_rows.fetchall()}

        peer_ids = sorted(
            {int(row["from_external_id"]) for row in raw_edges}
            | {int(row["to_external_id"]) for row in raw_edges}
        )
        by_id: dict[int, dict[str, Any]] = {}
        if peer_ids:
            found = await conn.execute(
                f"SELECT {PUBLIC_PEER_COLUMNS} FROM peers WHERE external_id = ANY(%s)",
                (peer_ids,),
            )
            for row in await found.fetchall():
                peer = public_peer(dict(row), data_dir=settings.data_dir)
                by_id[int(peer["external_id"])] = peer

        total_found = await conn.execute("SELECT COUNT(*)::bigint AS n FROM forward_edge_messages")
        total_row = await total_found.fetchone()
        message_forward_total = int(total_row["n"] or 0) if total_row else 0

        if include_messages:
            scoped_message_total = await _count_message_forwards(conn, where_sql, where_params)
            open_scope = message_scope_is_open(peer_id, date_from, date_to)
            if open_scope and scoped_message_total > MESSAGE_GRAPH_LIMIT:
                include_messages = False
                messages_omitted = True
                omit_reason = "unscoped_over_limit"
            else:
                message_rows, origin_by_key, messages_truncated = await _load_message_rows(
                    conn, where_sql, where_params
                )

    unique_neighbors: dict[int, set[int]] = {peer_id: set() for peer_id in peer_ids}
    volume: dict[int, int] = {peer_id: 0 for peer_id in peer_ids}
    unique_out: dict[int, int] = {peer_id: 0 for peer_id in peer_ids}
    total_out: dict[int, int] = {peer_id: 0 for peer_id in peer_ids}
    type_from_edge: dict[int, str] = {}
    name_from_edge: dict[int, str] = {}
    edges: list[dict[str, Any]] = []

    for row in raw_edges:
        src = int(row["from_external_id"])
        dst = int(row["to_external_id"])
        count = int(row["forward_count"] or 0)
        unique_neighbors.setdefault(src, set()).add(dst)
        unique_neighbors.setdefault(dst, set()).add(src)
        volume[src] = volume.get(src, 0) + count
        volume[dst] = volume.get(dst, 0) + count
        unique_out[src] = unique_out.get(src, 0) + 1
        total_out[src] = total_out.get(src, 0) + count
        from_type = str(row["from_peer_type"] or "").strip()
        to_type = str(row["to_peer_type"] or "").strip()
        if from_type:
            type_from_edge[src] = from_type
        if to_type:
            type_from_edge[dst] = to_type
        last_name = str(row.get("last_from_name") or "").strip()
        if last_name and src not in name_from_edge:
            name_from_edge[src] = last_name
        edges.append({"source": str(src), "target": str(dst), "count": count, "kind": "forward_from"})

    nodes: list[dict[str, Any]] = []
    for item_id in peer_ids:
        peer = by_id.get(item_id)
        messages_scraped = int(peer.get("messages_scraped") or 0) if peer else 0
        scraped = item_id in scraped_ids or messages_scraped > 0
        nodes.append(
            {
                "id": str(item_id),
                "kind": "peer",
                "external_id": item_id,
                "peer_type": (peer.get("peer_type") if peer else None)
                or type_from_edge.get(item_id)
                or "channel",
                "label": _peer_label(peer, name_from_edge.get(item_id)),
                "username": peer.get("username") if peer else None,
                "photo_url": peer.get("photo_url") if peer else None,
                "photo_media_kind": peer.get("photo_media_kind") if peer else None,
                "scraped": scraped,
                "is_scraping": bool(peer.get("is_scraping")) if peer else False,
                "scrape_detail": peer.get("scrape_detail") if peer else None,
                "degree": len(unique_neighbors.get(item_id, ())),
                "forward_volume": volume.get(item_id, 0),
                "forwards_unique": unique_out.get(item_id, 0),
                "forwards_total": total_out.get(item_id, 0),
            }
        )

    nodes.sort(
        key=lambda item: (-int(item["forward_volume"]), -int(item["degree"]), int(item["external_id"]))
    )
    message_nodes, message_edges = (
        build_message_layer(message_rows, origin_by_key) if include_messages else ([], [])
    )
    if message_nodes:
        nodes.extend(message_nodes)
        edges.extend(message_edges)

    peer_count = sum(1 for node in nodes if node.get("kind") != "message")
    message_count = sum(1 for node in nodes if node.get("kind") == "message")
    peer_edge_count = sum(1 for edge in edges if edge.get("kind") == "forward_from")
    estimated_nodes = peer_count + scoped_message_total
    estimated_edges = peer_edge_count + scoped_message_total * 2
    bytes_estimate = estimate_graph_bytes(peer_count, scoped_message_total, estimated_edges)
    open_scope = message_scope_is_open(peer_id, date_from, date_to)
    if open_scope:
        band = budget_band(estimated_nodes, estimated_edges, bytes_estimate)
    else:
        capped_nodes = peer_count + min(scoped_message_total, MESSAGE_GRAPH_LIMIT)
        capped_edges = peer_edge_count + min(scoped_message_total, MESSAGE_GRAPH_LIMIT) * 2
        band = budget_band(
            capped_nodes,
            capped_edges,
            estimate_graph_bytes(peer_count, min(scoped_message_total, MESSAGE_GRAPH_LIMIT), capped_edges),
        )
        if band == "block":
            band = "confirm"
    return {
        "nodes": nodes,
        "edges": edges,
        "meta": {
            "node_count": peer_count,
            "edge_count": peer_edge_count,
            "scraped_count": sum(1 for node in nodes if node.get("kind") != "message" and node.get("scraped")),
            "message_count": message_count,
            "messages_included": include_messages,
            "messages_truncated": messages_truncated,
            "messages_omitted": messages_omitted,
            "omit_reason": omit_reason,
            "message_forward_total": message_forward_total,
            "scoped_message_total": scoped_message_total,
            "returned_message_count": message_count,
            "bytes_estimate": bytes_estimate,
            "band": band,
            "limit": MESSAGE_GRAPH_LIMIT,
            "scope": _scope_meta(
                peer_id=peer_id,
                date_from=date_from,
                date_to=date_to,
                media=media_kinds,
            ),
        },
    }
    """Entire-catalog community forward graph (unique edges + counts)."""
    settings = load_settings()
    message_rows: list[dict[str, Any]] = []
    origin_by_key: dict[tuple[int, int], dict[str, Any]] = {}
    messages_truncated = False
    async with get_conn(settings) as conn:
        edge_rows = await conn.execute(
            """
            SELECT
                from_external_id, to_external_id, from_peer_type, to_peer_type,
                last_from_name, forward_count
            FROM forward_edges
            """
        )
        raw_edges = [dict(row) for row in await edge_rows.fetchall()]
        fetch_rows = await conn.execute("SELECT peer_external_id FROM peer_fetch_coverage")
        scraped_ids = {int(row["peer_external_id"]) for row in await fetch_rows.fetchall()}

        peer_ids = sorted(
            {int(row["from_external_id"]) for row in raw_edges}
            | {int(row["to_external_id"]) for row in raw_edges}
        )
        by_id: dict[int, dict[str, Any]] = {}
        if peer_ids:
            found = await conn.execute(
                f"SELECT {PUBLIC_PEER_COLUMNS} FROM peers WHERE external_id = ANY(%s)",
                (peer_ids,),
            )
            for row in await found.fetchall():
                peer = public_peer(dict(row), data_dir=settings.data_dir)
                by_id[int(peer["external_id"])] = peer

        if messages:
            kind_sql = _STORED_MEDIA_KIND_SQL.strip()
            found_messages = await conn.execute(
                f"""
                SELECT
                    m.id,
                    m.peer_external_id,
                    m.telegram_message_id,
                    m.date,
                    NULLIF(BTRIM(LEFT(m.content, 80)), '') AS excerpt,
                    m.fwd_from,
                    ({kind_sql}) AS media_kind
                FROM forward_edge_messages fem
                JOIN messages m ON m.id = fem.message_id
                ORDER BY m.date DESC NULLS LAST
                LIMIT %s
                """,
                (MESSAGE_GRAPH_LIMIT + 1,),
            )
            message_rows = [dict(row) for row in await found_messages.fetchall()]
            if len(message_rows) > MESSAGE_GRAPH_LIMIT:
                messages_truncated = True
                message_rows = message_rows[:MESSAGE_GRAPH_LIMIT]
            keys = origin_keys_from_forward_rows(message_rows)
            if keys:
                origin_found = await conn.execute(
                    f"""
                    SELECT
                        m.id,
                        m.peer_external_id,
                        m.telegram_message_id,
                        m.date,
                        NULLIF(BTRIM(LEFT(m.content, 80)), '') AS excerpt,
                        ({kind_sql}) AS media_kind,
                        (m.fwd_from IS NOT NULL) AS forwarded
                    FROM messages m
                    WHERE (m.peer_external_id, m.telegram_message_id) IN (
                        SELECT * FROM unnest(%s::bigint[], %s::integer[])
                    )
                    """,
                    ([peer for peer, _mid in keys], [mid for _peer, mid in keys]),
                )
                for row in await origin_found.fetchall():
                    origin_by_key[(int(row["peer_external_id"]), int(row["telegram_message_id"]))] = dict(
                        row
                    )

    unique_neighbors: dict[int, set[int]] = {peer_id: set() for peer_id in peer_ids}
    volume: dict[int, int] = {peer_id: 0 for peer_id in peer_ids}
    unique_out: dict[int, int] = {peer_id: 0 for peer_id in peer_ids}
    total_out: dict[int, int] = {peer_id: 0 for peer_id in peer_ids}
    type_from_edge: dict[int, str] = {}
    name_from_edge: dict[int, str] = {}
    edges: list[dict[str, Any]] = []

    for row in raw_edges:
        src = int(row["from_external_id"])
        dst = int(row["to_external_id"])
        count = int(row["forward_count"] or 0)
        unique_neighbors.setdefault(src, set()).add(dst)
        unique_neighbors.setdefault(dst, set()).add(src)
        volume[src] = volume.get(src, 0) + count
        volume[dst] = volume.get(dst, 0) + count
        unique_out[src] = unique_out.get(src, 0) + 1
        total_out[src] = total_out.get(src, 0) + count
        from_type = str(row["from_peer_type"] or "").strip()
        to_type = str(row["to_peer_type"] or "").strip()
        if from_type:
            type_from_edge[src] = from_type
        if to_type:
            type_from_edge[dst] = to_type
        last_name = str(row.get("last_from_name") or "").strip()
        if last_name and src not in name_from_edge:
            name_from_edge[src] = last_name
        edges.append({"source": str(src), "target": str(dst), "count": count, "kind": "forward_from"})

    nodes: list[dict[str, Any]] = []
    for peer_id in peer_ids:
        peer = by_id.get(peer_id)
        messages_scraped = int(peer.get("messages_scraped") or 0) if peer else 0
        scraped = peer_id in scraped_ids or messages_scraped > 0
        nodes.append(
            {
                "id": str(peer_id),
                "kind": "peer",
                "external_id": peer_id,
                "peer_type": (peer.get("peer_type") if peer else None)
                or type_from_edge.get(peer_id)
                or "channel",
                "label": _peer_label(peer, name_from_edge.get(peer_id)),
                "username": peer.get("username") if peer else None,
                "photo_url": peer.get("photo_url") if peer else None,
                "photo_media_kind": peer.get("photo_media_kind") if peer else None,
                "scraped": scraped,
                "is_scraping": bool(peer.get("is_scraping")) if peer else False,
                "scrape_detail": peer.get("scrape_detail") if peer else None,
                "degree": len(unique_neighbors.get(peer_id, ())),
                "forward_volume": volume.get(peer_id, 0),
                "forwards_unique": unique_out.get(peer_id, 0),
                "forwards_total": total_out.get(peer_id, 0),
            }
        )

    nodes.sort(
        key=lambda item: (-int(item["forward_volume"]), -int(item["degree"]), int(item["external_id"]))
    )
    message_nodes, message_edges = build_message_layer(message_rows, origin_by_key) if messages else ([], [])
    if message_nodes:
        nodes.extend(message_nodes)
        edges.extend(message_edges)

    peer_count = sum(1 for node in nodes if node.get("kind") != "message")
    message_count = sum(1 for node in nodes if node.get("kind") == "message")
    return {
        "nodes": nodes,
        "edges": edges,
        "meta": {
            "node_count": peer_count,
            "edge_count": sum(1 for edge in edges if edge.get("kind") == "forward_from"),
            "scraped_count": sum(1 for node in nodes if node.get("kind") != "message" and node.get("scraped")),
            "message_count": message_count,
            "messages_included": messages,
            "messages_truncated": messages_truncated,
        },
    }


def shared_image_date_sql(
    *,
    date_from: datetime | None,
    date_to: datetime | None,
) -> tuple[str, list[Any]]:
    clauses: list[str] = ["TRUE"]
    params: list[Any] = []
    if date_from is not None:
        clauses.append("ibm.message_date >= %s")
        params.append(date_from)
    if date_to is not None:
        clauses.append("ibm.message_date <= %s")
        params.append(date_to)
    return " AND ".join(clauses), params


def _image_node(
    *,
    phash: str,
    unique_peers: int,
    appearances: int,
    first_seen: Any,
) -> dict[str, Any]:
    label = f"{unique_peers} peers"
    return {
        "id": f"img:{phash}",
        "kind": "image",
        "external_id": 0,
        "peer_type": "image",
        "label": label,
        "username": None,
        "photo_url": f"/api/images/{phash}/file",
        "scraped": True,
        "is_scraping": False,
        "degree": unique_peers,
        "forward_volume": appearances,
        "forwards_unique": unique_peers,
        "forwards_total": appearances,
        "media_kind": "image",
        "date": _iso(first_seen),
        "phash": phash,
        "excerpt": label,
    }


async def _count_shared_images(
    conn: Any,
    date_sql: str,
    date_params: list[Any],
    peer_id: int | None,
) -> int:
    peer_sql = ""
    params: list[Any] = [*date_params]
    if peer_id is not None:
        peer_sql = """
          AND EXISTS (
            SELECT 1
            FROM appearances hit
            WHERE hit.phash = shared.phash
              AND hit.peer_external_id = %s
          )
        """
        params.append(peer_id)
    found = await conn.execute(
        f"""
        WITH appearances AS (
          SELECT ibm.phash, ibm.peer_external_id
          FROM image_blob_messages ibm
          WHERE {date_sql}
          GROUP BY ibm.phash, ibm.peer_external_id
        ),
        shared AS (
          SELECT phash
          FROM appearances
          GROUP BY phash
          HAVING COUNT(*) >= %s
        )
        SELECT COUNT(*)::bigint AS n
        FROM shared
        WHERE TRUE
        {peer_sql}
        """,
        (*params[: len(date_params)], MIN_SHARED_IMAGE_PEERS, *params[len(date_params) :]),
    )
    row = await found.fetchone()
    return int(row["n"] or 0) if row else 0


async def _load_shared_image_rows(
    conn: Any,
    date_sql: str,
    date_params: list[Any],
    peer_id: int | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], bool]:
    peer_sql = ""
    top_params: list[Any] = [*date_params, MIN_SHARED_IMAGE_PEERS]
    if peer_id is not None:
        peer_sql = """
          AND EXISTS (
            SELECT 1
            FROM appearances hit
            WHERE hit.phash = shared.phash
              AND hit.peer_external_id = %s
          )
        """
        top_params.append(peer_id)
    top_params.append(IMAGE_GRAPH_LIMIT + 1)
    found = await conn.execute(
        f"""
        WITH appearances AS (
          SELECT
            ibm.phash,
            ibm.peer_external_id,
            COUNT(*)::int AS appearances,
            MIN(ibm.message_date) AS first_seen
          FROM image_blob_messages ibm
          WHERE {date_sql}
          GROUP BY ibm.phash, ibm.peer_external_id
        ),
        shared AS (
          SELECT
            phash,
            COUNT(*)::int AS unique_peers,
            SUM(appearances)::int AS appearances,
            MIN(first_seen) AS first_seen
          FROM appearances
          GROUP BY phash
          HAVING COUNT(*) >= %s
        )
        SELECT phash, unique_peers, appearances, first_seen
        FROM shared
        WHERE TRUE
        {peer_sql}
        ORDER BY unique_peers DESC, appearances DESC, phash
        LIMIT %s
        """,
        tuple(top_params),
    )
    image_rows = [dict(row) for row in await found.fetchall()]
    truncated = len(image_rows) > IMAGE_GRAPH_LIMIT
    if truncated:
        image_rows = image_rows[:IMAGE_GRAPH_LIMIT]
    phashes = [str(row["phash"]) for row in image_rows]
    edge_rows: list[dict[str, Any]] = []
    if phashes:
        edges_found = await conn.execute(
            f"""
            SELECT
              ibm.phash,
              ibm.peer_external_id,
              COUNT(*)::int AS appearances
            FROM image_blob_messages ibm
            WHERE ibm.phash = ANY(%s)
              AND {date_sql}
            GROUP BY ibm.phash, ibm.peer_external_id
            """,
            (phashes, *date_params),
        )
        edge_rows = [dict(row) for row in await edges_found.fetchall()]
    return image_rows, edge_rows, truncated


@router.get("/graph/shared-images/stats")
async def catalog_shared_image_graph_stats(
    peer_id: int | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
) -> dict[str, Any]:
    settings = load_settings()
    date_sql, date_params = shared_image_date_sql(date_from=date_from, date_to=date_to)
    async with get_conn(settings) as conn:
        scoped_image_count = await _count_shared_images(conn, date_sql, date_params, peer_id)
        edge_found = await conn.execute(
            f"""
            WITH appearances AS (
              SELECT ibm.phash, ibm.peer_external_id
              FROM image_blob_messages ibm
              WHERE {date_sql}
              GROUP BY ibm.phash, ibm.peer_external_id
            ),
            shared AS (
              SELECT phash
              FROM appearances
              GROUP BY phash
              HAVING COUNT(*) >= %s
            )
            SELECT
              COUNT(*)::bigint AS edge_count,
              COUNT(DISTINCT appearances.peer_external_id)::bigint AS peer_count
            FROM appearances
            JOIN shared ON shared.phash = appearances.phash
            """,
            (*date_params, MIN_SHARED_IMAGE_PEERS),
        )
        edge_row = await edge_found.fetchone()
        # Neighborhood stats should describe the selected peer's shared images, not the catalog.
        if peer_id is not None:
            scoped_found = await conn.execute(
                f"""
                WITH appearances AS (
                  SELECT ibm.phash, ibm.peer_external_id
                  FROM image_blob_messages ibm
                  WHERE {date_sql}
                  GROUP BY ibm.phash, ibm.peer_external_id
                ),
                shared AS (
                  SELECT phash
                  FROM appearances
                  GROUP BY phash
                  HAVING COUNT(*) >= %s
                ),
                focused AS (
                  SELECT shared.phash
                  FROM shared
                  WHERE EXISTS (
                    SELECT 1 FROM appearances hit
                    WHERE hit.phash = shared.phash AND hit.peer_external_id = %s
                  )
                )
                SELECT
                  COUNT(*)::bigint AS edge_count,
                  COUNT(DISTINCT appearances.peer_external_id)::bigint AS peer_count
                FROM appearances
                JOIN focused ON focused.phash = appearances.phash
                """,
                (*date_params, MIN_SHARED_IMAGE_PEERS, peer_id),
            )
            edge_row = await scoped_found.fetchone()

    image_count = scoped_image_count
    peer_count = int(edge_row["peer_count"] or 0) if edge_row else 0
    edge_count = int(edge_row["edge_count"] or 0) if edge_row else 0
    estimated_nodes = peer_count + image_count
    estimated_edges = edge_count
    bytes_estimate = estimate_graph_bytes(peer_count, image_count, estimated_edges)
    open_scope = message_scope_is_open(peer_id, date_from, date_to)
    if open_scope:
        band = budget_band(estimated_nodes, estimated_edges, bytes_estimate)
    else:
        capped_images = min(image_count, IMAGE_GRAPH_LIMIT)
        capped_nodes = peer_count + capped_images
        capped_edges = min(edge_count, IMAGE_GRAPH_LIMIT * 8)
        band = budget_band(
            capped_nodes,
            capped_edges,
            estimate_graph_bytes(peer_count, capped_images, capped_edges),
        )
        if band == "block":
            band = "confirm"
    return {
        "peer_count": peer_count,
        "image_count": image_count,
        "edge_count": edge_count,
        "scoped_image_count": scoped_image_count,
        "estimated_nodes": estimated_nodes,
        "estimated_edges": estimated_edges,
        "bytes_estimate": bytes_estimate,
        "band": band,
        "limit": IMAGE_GRAPH_LIMIT,
        "scope": _scope_meta(
            peer_id=peer_id,
            date_from=date_from,
            date_to=date_to,
            media={"image"},
        ),
    }


@router.get("/graph/shared-images")
async def catalog_shared_image_graph(
    peer_id: int | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
) -> dict[str, Any]:
    """Bipartite graph: unique images that appear in 2+ peers, linked to those peers."""
    settings = load_settings()
    date_sql, date_params = shared_image_date_sql(date_from=date_from, date_to=date_to)
    image_rows: list[dict[str, Any]] = []
    edge_rows: list[dict[str, Any]] = []
    truncated = False
    omitted = False
    omit_reason: str | None = None
    scoped_total = 0
    include = True
    async with get_conn(settings) as conn:
        scoped_total = await _count_shared_images(conn, date_sql, date_params, peer_id)
        open_scope = message_scope_is_open(peer_id, date_from, date_to)
        if open_scope and scoped_total > IMAGE_GRAPH_LIMIT:
            include = False
            omitted = True
            omit_reason = "unscoped_over_limit"
        elif include:
            image_rows, edge_rows, truncated = await _load_shared_image_rows(
                conn, date_sql, date_params, peer_id
            )

        peer_ids = sorted({int(row["peer_external_id"]) for row in edge_rows})
        by_id: dict[int, dict[str, Any]] = {}
        scraped_ids: set[int] = set()
        if peer_ids:
            found = await conn.execute(
                f"SELECT {PUBLIC_PEER_COLUMNS} FROM peers WHERE external_id = ANY(%s)",
                (peer_ids,),
            )
            for row in await found.fetchall():
                peer = public_peer(dict(row), data_dir=settings.data_dir)
                by_id[int(peer["external_id"])] = peer
            fetch_rows = await conn.execute(
                "SELECT peer_external_id FROM peer_fetch_coverage WHERE peer_external_id = ANY(%s)",
                (peer_ids,),
            )
            scraped_ids = {int(row["peer_external_id"]) for row in await fetch_rows.fetchall()}

    image_stats = {
        str(row["phash"]): {
            "unique_peers": int(row["unique_peers"] or 0),
            "appearances": int(row["appearances"] or 0),
            "first_seen": row.get("first_seen"),
        }
        for row in image_rows
    }
    peer_images: dict[int, int] = {}
    peer_volume: dict[int, int] = {}
    edges: list[dict[str, Any]] = []
    for row in edge_rows:
        phash = str(row["phash"])
        if phash not in image_stats:
            continue
        peer = int(row["peer_external_id"])
        count = int(row["appearances"] or 0)
        peer_images[peer] = peer_images.get(peer, 0) + 1
        peer_volume[peer] = peer_volume.get(peer, 0) + count
        edges.append(
            {
                "source": f"img:{phash}",
                "target": str(peer),
                "count": count,
                "kind": "appeared_in",
            }
        )

    nodes: list[dict[str, Any]] = []
    for item_id in peer_ids:
        peer = by_id.get(item_id)
        messages_scraped = int(peer.get("messages_scraped") or 0) if peer else 0
        scraped = item_id in scraped_ids or messages_scraped > 0
        degree = peer_images.get(item_id, 0)
        volume = peer_volume.get(item_id, 0)
        nodes.append(
            {
                "id": str(item_id),
                "kind": "peer",
                "external_id": item_id,
                "peer_type": (peer.get("peer_type") if peer else None) or "channel",
                "label": _peer_label(peer),
                "username": peer.get("username") if peer else None,
                "photo_url": peer.get("photo_url") if peer else None,
                "photo_media_kind": peer.get("photo_media_kind") if peer else None,
                "scraped": scraped,
                "is_scraping": bool(peer.get("is_scraping")) if peer else False,
                "scrape_detail": peer.get("scrape_detail") if peer else None,
                "degree": degree,
                "forward_volume": volume,
                "forwards_unique": degree,
                "forwards_total": volume,
            }
        )
    nodes.sort(key=lambda item: (-int(item["forward_volume"]), -int(item["degree"]), int(item["external_id"])))
    image_nodes = [
        _image_node(
            phash=phash,
            unique_peers=stats["unique_peers"],
            appearances=stats["appearances"],
            first_seen=stats["first_seen"],
        )
        for phash, stats in image_stats.items()
    ]
    image_nodes.sort(key=lambda item: (-int(item["degree"]), -int(item["forward_volume"]), str(item["id"])))
    nodes.extend(image_nodes)

    peer_count = sum(1 for node in nodes if node.get("kind") == "peer")
    image_count = sum(1 for node in nodes if node.get("kind") == "image")
    estimated_nodes = peer_count + scoped_total
    estimated_edges = len(edges) if include else scoped_total * 3
    bytes_estimate = estimate_graph_bytes(peer_count, scoped_total, estimated_edges)
    open_scope = message_scope_is_open(peer_id, date_from, date_to)
    if open_scope:
        band = budget_band(estimated_nodes, estimated_edges, bytes_estimate)
    else:
        band = "auto"
    return {
        "nodes": nodes,
        "edges": edges,
        "meta": {
            "node_count": peer_count,
            "edge_count": len(edges),
            "scraped_count": sum(1 for node in nodes if node.get("kind") == "peer" and node.get("scraped")),
            "image_count": image_count,
            "images_included": include,
            "images_truncated": truncated,
            "images_omitted": omitted,
            "omit_reason": omit_reason,
            "scoped_image_total": scoped_total,
            "returned_image_count": image_count,
            "bytes_estimate": bytes_estimate,
            "band": band,
            "limit": IMAGE_GRAPH_LIMIT,
            "scope": _scope_meta(
                peer_id=peer_id,
                date_from=date_from,
                date_to=date_to,
                media={"image"},
            ),
        },
    }
