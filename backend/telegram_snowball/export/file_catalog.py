from __future__ import annotations

from typing import Any

from telegram_snowball.catalog import stored_kind_is
from telegram_snowball.export.files import download_response, export_stamp, write_csv, write_json, write_zip
from telegram_snowball.telegram.profile import usernames_csv

_FILE_SELECT = """
    COALESCE(NULLIF(media->>'document_id', ''), 'msg:' || id::text) AS file_id,
    MAX(
        CASE
            WHEN (media->>'size_bytes') ~ '^[0-9]+$'
            THEN (media->>'size_bytes')::bigint
        END
    ) AS size_bytes,
    MAX(media->>'mime_type') AS mime_type,
    MAX(media->>'file_name') AS file_name,
    BOOL_OR(
        COALESCE((media->>'downloaded') IN ('true', 't', '1'), false)
        AND NULLIF(media->>'path', '') IS NOT NULL
    ) AS persisted,
    COUNT(*) AS appearances,
    COUNT(DISTINCT peer_external_id) AS unique_peers,
    MAX(date) AS last_seen_at
"""

FILE_CSV_COLUMNS = [
    "file_id",
    "file_name",
    "mime_type",
    "size_bytes",
    "appearances",
    "unique_peers",
    "last_seen_at",
    "persisted",
]
FILE_PEER_CSV_COLUMNS = [
    "file_id",
    "peer_external_id",
    "peer_type",
    "peer_title",
    "peer_username",
    "peer_usernames",
    "appearances",
    "forwarded",
]


async def _load_file_rows(conn: Any, *, peer_external_id: int | None) -> list[dict[str, Any]]:
    if peer_external_id is not None:
        rows = await conn.execute(
            f"""
            SELECT {_FILE_SELECT}
            FROM messages
            WHERE {stored_kind_is("document")}
              AND COALESCE(NULLIF(media->>'document_id', ''), 'msg:' || id::text) IN (
                SELECT COALESCE(NULLIF(media->>'document_id', ''), 'msg:' || id::text)
                FROM messages
                WHERE {stored_kind_is("document")}
                  AND peer_external_id = %s
              )
            GROUP BY 1
            ORDER BY last_seen_at DESC NULLS LAST, file_id
            """,
            (peer_external_id,),
        )
    else:
        rows = await conn.execute(
            f"""
            SELECT {_FILE_SELECT}
            FROM messages
            WHERE {stored_kind_is("document")}
            GROUP BY 1
            ORDER BY last_seen_at DESC NULLS LAST, file_id
            """
        )
    return [dict(row) for row in await rows.fetchall()]


async def _load_file_peer_rows(conn: Any, file_ids: list[str]) -> list[dict[str, Any]]:
    if not file_ids:
        return []
    doc_ids = [file_id for file_id in file_ids if not file_id.startswith("msg:")]
    msg_ids = [file_id[4:] for file_id in file_ids if file_id.startswith("msg:")]
    fan_rows: list[dict[str, Any]] = []
    if doc_ids:
        rows = await conn.execute(
            f"""
            SELECT
                media->>'document_id' AS file_id,
                peer_external_id,
                COUNT(*) AS appearances,
                COUNT(*) FILTER (WHERE fwd_from IS NOT NULL) AS forwarded,
                p.peer_type, p.title AS peer_title, p.username AS peer_username,
                p.usernames AS peer_usernames
            FROM messages
            JOIN peers p ON p.external_id = messages.peer_external_id
            WHERE {stored_kind_is("document")}
              AND media->>'document_id' = ANY(%s)
            GROUP BY media->>'document_id', peer_external_id, p.peer_type, p.title, p.username, p.usernames
            ORDER BY file_id, appearances DESC, peer_external_id
            """,
            (doc_ids,),
        )
        fan_rows.extend(dict(row) for row in await rows.fetchall())
    if msg_ids:
        rows = await conn.execute(
            f"""
            SELECT
                'msg:' || messages.id::text AS file_id,
                peer_external_id,
                1 AS appearances,
                CASE WHEN fwd_from IS NOT NULL THEN 1 ELSE 0 END AS forwarded,
                p.peer_type, p.title AS peer_title, p.username AS peer_username,
                p.usernames AS peer_usernames
            FROM messages
            JOIN peers p ON p.external_id = messages.peer_external_id
            WHERE messages.id = ANY(%s::uuid[])
              AND {stored_kind_is("document")}
            """,
            (msg_ids,),
        )
        fan_rows.extend(dict(row) for row in await rows.fetchall())
    return fan_rows


def _flatten_file_peer(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "file_id": row.get("file_id"),
        "peer_external_id": row.get("peer_external_id"),
        "peer_type": row.get("peer_type"),
        "peer_title": row.get("peer_title"),
        "peer_username": row.get("peer_username"),
        "peer_usernames": usernames_csv(row.get("peer_usernames")),
        "appearances": int(row.get("appearances") or 0),
        "forwarded": int(row.get("forwarded") or 0),
    }


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


async def export_catalog_files(conn: Any, *, fmt: str, peer_external_id: int | None):
    files = await _load_file_rows(conn, peer_external_id=peer_external_id)
    ids = [str(row["file_id"]) for row in files]
    fans = await _load_file_peer_rows(conn, ids)
    stamp = export_stamp()
    suffix = f"-peer-{peer_external_id}" if peer_external_id is not None else ""
    if fmt == "json":
        grouped: dict[str, list[dict[str, Any]]] = {file_id: [] for file_id in ids}
        for row in fans:
            grouped.setdefault(str(row["file_id"]), []).append(
                {
                    "external_id": row.get("peer_external_id"),
                    "peer_type": row.get("peer_type"),
                    "title": row.get("peer_title"),
                    "username": row.get("peer_username"),
                    "usernames": row.get("peer_usernames") or [],
                    "appearances": int(row.get("appearances") or 0),
                    "forwarded": int(row.get("forwarded") or 0),
                }
            )
        payload = {
            "exported_at": stamp,
            "filters": {"peer_external_id": peer_external_id},
            "count": len(files),
            "files": [
                {
                    "id": row["file_id"],
                    "file_name": row.get("file_name"),
                    "mime_type": row.get("mime_type"),
                    "size_bytes": _int_or_none(row.get("size_bytes")),
                    "appearances": int(row.get("appearances") or 0),
                    "unique_peers": int(row.get("unique_peers") or 0),
                    "last_seen_at": row.get("last_seen_at"),
                    "persisted": bool(row.get("persisted")),
                    "peers": grouped.get(str(row["file_id"]), []),
                }
                for row in files
            ],
        }
        return download_response(
            write_json(payload),
            filename=f"snowball-files{suffix}-{stamp}.json",
            media_type="application/json",
        )
    file_rows = [
        {
            "file_id": row["file_id"],
            "file_name": row.get("file_name"),
            "mime_type": row.get("mime_type"),
            "size_bytes": _int_or_none(row.get("size_bytes")),
            "appearances": int(row.get("appearances") or 0),
            "unique_peers": int(row.get("unique_peers") or 0),
            "last_seen_at": row.get("last_seen_at"),
            "persisted": bool(row.get("persisted")),
        }
        for row in files
    ]
    archive = {
        "files.csv": write_csv(file_rows, FILE_CSV_COLUMNS),
        "file_peers.csv": write_csv([_flatten_file_peer(row) for row in fans], FILE_PEER_CSV_COLUMNS),
    }
    return download_response(
        write_zip(archive),
        filename=f"snowball-files{suffix}-{stamp}.zip",
        media_type="application/zip",
    )
