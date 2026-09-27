from __future__ import annotations

from datetime import datetime
from typing import Any

from telegram_snowball.export.files import download_response, export_stamp, write_csv, write_json
from telegram_snowball.telegram.forwards import fwd_from_name, signed_peer_from_fwd
from telegram_snowball.telegram.media_kinds import media_kind_from_stored
from telegram_snowball.telegram.profile import usernames_csv

MESSAGE_CSV_COLUMNS = [
    "id",
    "telegram_message_id",
    "date",
    "peer_external_id",
    "peer_type",
    "peer_title",
    "peer_username",
    "peer_usernames",
    "from_external_id",
    "content",
    "forwarded",
    "fwd_from_peer_id",
    "fwd_from_name",
    "media_kind",
    "media_document_id",
    "media_mime_type",
    "media_file_name",
    "media_size_bytes",
    "media_duration",
    "media_width",
    "media_height",
    "image_phash",
    "text_embedded",
    "image_embedded",
]


def _media_field(media: Any, key: str) -> Any:
    if not isinstance(media, dict):
        return None
    value = media.get(key)
    return value if value not in ("", None) else None


def flatten_message(row: dict[str, Any], *, include_forwards: bool) -> dict[str, Any]:
    media = row.get("media") if isinstance(row.get("media"), dict) else None
    fwd = row.get("fwd_from") if include_forwards else None
    return {
        "id": row.get("id"),
        "telegram_message_id": row.get("telegram_message_id"),
        "date": row.get("date"),
        "peer_external_id": row.get("peer_external_id"),
        "peer_type": row.get("peer_type"),
        "peer_title": row.get("peer_title"),
        "peer_username": row.get("peer_username"),
        "peer_usernames": usernames_csv(row.get("peer_usernames")),
        "from_external_id": row.get("from_external_id"),
        "content": row.get("content"),
        "forwarded": row.get("fwd_from") is not None,
        "fwd_from_peer_id": signed_peer_from_fwd(fwd) if fwd is not None else None,
        "fwd_from_name": fwd_from_name(fwd) if fwd is not None else None,
        "media_kind": media_kind_from_stored(media),
        "media_document_id": _media_field(media, "document_id"),
        "media_mime_type": _media_field(media, "mime_type"),
        "media_file_name": _media_field(media, "file_name"),
        "media_size_bytes": _media_field(media, "size_bytes"),
        "media_duration": _media_field(media, "duration"),
        "media_width": _media_field(media, "width"),
        "media_height": _media_field(media, "height"),
        "image_phash": row.get("image_phash"),
        "text_embedded": bool(row.get("text_embedded")),
        "image_embedded": bool(row.get("image_embedded")),
    }


def json_message(row: dict[str, Any], *, include_forwards: bool) -> dict[str, Any]:
    media = row.get("media") if isinstance(row.get("media"), dict) else None
    kind = media_kind_from_stored(media)
    media_out = None
    if kind:
        media_out = {
            "kind": kind,
            "document_id": _media_field(media, "document_id"),
            "mime_type": _media_field(media, "mime_type"),
            "file_name": _media_field(media, "file_name"),
            "size_bytes": _media_field(media, "size_bytes"),
            "duration": _media_field(media, "duration"),
            "width": _media_field(media, "width"),
            "height": _media_field(media, "height"),
            "phash": row.get("image_phash"),
        }
        media_out = {key: value for key, value in media_out.items() if value is not None}
    fwd = row.get("fwd_from") if include_forwards else None
    forward = None
    if fwd is not None:
        forward = {
            "from_peer_id": signed_peer_from_fwd(fwd),
            "from_name": fwd_from_name(fwd),
        }
    return {
        "id": str(row.get("id")) if row.get("id") is not None else None,
        "telegram_message_id": row.get("telegram_message_id"),
        "date": row.get("date"),
        "from_external_id": row.get("from_external_id"),
        "content": row.get("content"),
        "forward": forward,
        "media": media_out or None,
        "text_embedded": bool(row.get("text_embedded")),
        "image_embedded": bool(row.get("image_embedded")),
    }


async def load_export_messages(
    conn: Any,
    *,
    peer_external_id: int | None,
    date_from: datetime | None,
    date_to: datetime | None,
    text_only: bool,
    media_only: bool,
) -> list[dict[str, Any]]:
    clauses = ["TRUE"]
    params: list[Any] = []
    if peer_external_id is not None:
        clauses.append("m.peer_external_id = %s")
        params.append(peer_external_id)
    if date_from is not None:
        clauses.append("m.date >= %s")
        params.append(date_from)
    if date_to is not None:
        clauses.append("m.date <= %s")
        params.append(date_to)
    if text_only:
        clauses.append("NULLIF(BTRIM(m.content), '') IS NOT NULL")
    if media_only:
        clauses.append("m.media->>'kind' IS NOT NULL")
    where = " AND ".join(clauses)
    rows = await conn.execute(
        f"""
        SELECT
            m.id, m.telegram_message_id, m.date, m.content, m.from_external_id,
            m.fwd_from, m.media, m.text_embedded, m.image_embedded,
            p.external_id AS peer_external_id, p.peer_type,
            p.title AS peer_title, p.username AS peer_username, p.usernames AS peer_usernames,
            ibm.phash AS image_phash
        FROM messages m
        JOIN peers p ON p.external_id = m.peer_external_id
        LEFT JOIN LATERAL (
            SELECT phash FROM image_blob_messages
            WHERE message_id = m.id
            ORDER BY phash
            LIMIT 1
        ) ibm ON TRUE
        WHERE {where}
        ORDER BY p.title NULLS LAST, p.external_id, m.date ASC, m.telegram_message_id ASC
        """,
        tuple(params),
    )
    return [dict(row) for row in await rows.fetchall()]


async def export_messages(
    conn: Any,
    *,
    fmt: str,
    peer_external_id: int | None,
    date_from: datetime | None,
    date_to: datetime | None,
    text_only: bool,
    media_only: bool,
    include_forwards: bool,
):
    rows = await load_export_messages(
        conn,
        peer_external_id=peer_external_id,
        date_from=date_from,
        date_to=date_to,
        text_only=text_only,
        media_only=media_only,
    )
    stamp = export_stamp()
    suffix = f"-peer-{peer_external_id}" if peer_external_id is not None else ""
    filters = {
        "peer_external_id": peer_external_id,
        "date_from": date_from,
        "date_to": date_to,
        "text_only": text_only,
        "media_only": media_only,
        "include_forwards": include_forwards,
    }
    if fmt == "json":
        grouped: dict[int, dict[str, Any]] = {}
        order: list[int] = []
        for row in rows:
            peer_id = int(row["peer_external_id"])
            if peer_id not in grouped:
                grouped[peer_id] = {
                    "external_id": peer_id,
                    "peer_type": row.get("peer_type"),
                    "title": row.get("peer_title"),
                    "username": row.get("peer_username"),
                    "usernames": row.get("peer_usernames") or [],
                    "messages": [],
                }
                order.append(peer_id)
            grouped[peer_id]["messages"].append(json_message(row, include_forwards=include_forwards))
        payload = {
            "exported_at": stamp,
            "filters": filters,
            "count": len(rows),
            "peers": [grouped[peer_id] for peer_id in order],
        }
        return download_response(
            write_json(payload),
            filename=f"snowball-messages{suffix}-{stamp}.json",
            media_type="application/json",
        )
    csv_rows = [flatten_message(row, include_forwards=include_forwards) for row in rows]
    return download_response(
        write_csv(csv_rows, MESSAGE_CSV_COLUMNS),
        filename=f"snowball-messages{suffix}-{stamp}.csv",
        media_type="text/csv",
    )
