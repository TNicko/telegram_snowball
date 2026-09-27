from __future__ import annotations

from typing import Any

from telegram_snowball.export.files import download_response, export_stamp, write_csv, write_json, write_zip
from telegram_snowball.telegram.profile import usernames_csv

IMAGE_CSV_COLUMNS = [
    "phash",
    "appearances",
    "unique_peers",
    "last_seen_at",
    "persisted",
    "refcount",
]
IMAGE_PEER_CSV_COLUMNS = [
    "phash",
    "peer_external_id",
    "peer_type",
    "peer_title",
    "peer_username",
    "peer_usernames",
    "appearances",
    "forwarded",
]


async def _load_image_rows(
    conn: Any,
    *,
    peer_external_id: int | None,
) -> list[dict[str, Any]]:
    clauses = ["TRUE"]
    params: list[Any] = []
    if peer_external_id is not None:
        clauses.append(
            """
            EXISTS (
                SELECT 1 FROM image_blob_messages hit
                WHERE hit.phash = b.phash AND hit.peer_external_id = %s
            )
            """
        )
        params.append(peer_external_id)
    where = " AND ".join(clauses)
    rows = await conn.execute(
        f"""
        SELECT
            b.phash,
            b.canonical_path,
            b.refcount,
            COUNT(m.message_id) AS appearances,
            COUNT(DISTINCT m.peer_external_id) AS unique_peers,
            MAX(m.message_date) AS last_seen_at
        FROM image_blobs b
        LEFT JOIN image_blob_messages m ON m.phash = b.phash
        WHERE {where}
        GROUP BY b.phash, b.canonical_path, b.refcount
        ORDER BY unique_peers DESC, appearances DESC, last_seen_at DESC NULLS LAST, b.phash
        """,
        tuple(params),
    )
    return [dict(row) for row in await rows.fetchall()]


async def _load_image_peer_rows(conn: Any, phashes: list[str]) -> list[dict[str, Any]]:
    if not phashes:
        return []
    rows = await conn.execute(
        """
        SELECT
            ibm.phash,
            ibm.peer_external_id,
            COUNT(*) AS appearances,
            COUNT(*) FILTER (WHERE msg.fwd_from IS NOT NULL) AS forwarded,
            p.peer_type, p.title AS peer_title, p.username AS peer_username,
            p.usernames AS peer_usernames
        FROM image_blob_messages ibm
        JOIN messages msg ON msg.id = ibm.message_id
        JOIN peers p ON p.external_id = ibm.peer_external_id
        WHERE ibm.phash = ANY(%s)
        GROUP BY ibm.phash, ibm.peer_external_id, p.peer_type, p.title, p.username, p.usernames
        ORDER BY ibm.phash, appearances DESC, ibm.peer_external_id
        """,
        (phashes,),
    )
    return [dict(row) for row in await rows.fetchall()]


def _is_persisted(row: dict[str, Any]) -> bool:
    return bool(row.get("canonical_path"))


def _flatten_image_peer(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "phash": row.get("phash"),
        "peer_external_id": row.get("peer_external_id"),
        "peer_type": row.get("peer_type"),
        "peer_title": row.get("peer_title"),
        "peer_username": row.get("peer_username"),
        "peer_usernames": usernames_csv(row.get("peer_usernames")),
        "appearances": int(row.get("appearances") or 0),
        "forwarded": int(row.get("forwarded") or 0),
    }


async def export_images(
    conn: Any,
    *,
    fmt: str,
    peer_external_id: int | None,
):
    images = await _load_image_rows(
        conn,
        peer_external_id=peer_external_id,
    )
    phashes = [str(row["phash"]) for row in images]
    fans = await _load_image_peer_rows(conn, phashes)
    stamp = export_stamp()
    suffix = f"-peer-{peer_external_id}" if peer_external_id is not None else ""
    if fmt == "json":
        grouped: dict[str, list[dict[str, Any]]] = {phash: [] for phash in phashes}
        for row in fans:
            grouped.setdefault(str(row["phash"]), []).append(
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
            "count": len(images),
            "images": [
                {
                    "phash": row["phash"],
                    "appearances": int(row.get("appearances") or 0),
                    "unique_peers": int(row.get("unique_peers") or 0),
                    "last_seen_at": row.get("last_seen_at"),
                    "refcount": int(row.get("refcount") or 0),
                    "persisted": _is_persisted(row),
                    "peers": grouped.get(str(row["phash"]), []),
                }
                for row in images
            ],
        }
        return download_response(
            write_json(payload),
            filename=f"snowball-images{suffix}-{stamp}.json",
            media_type="application/json",
        )
    image_rows = [
        {
            "phash": row["phash"],
            "appearances": int(row.get("appearances") or 0),
            "unique_peers": int(row.get("unique_peers") or 0),
            "last_seen_at": row.get("last_seen_at"),
            "persisted": _is_persisted(row),
            "refcount": int(row.get("refcount") or 0),
        }
        for row in images
    ]
    files = {
        "images.csv": write_csv(image_rows, IMAGE_CSV_COLUMNS),
        "image_peers.csv": write_csv([_flatten_image_peer(row) for row in fans], IMAGE_PEER_CSV_COLUMNS),
    }
    return download_response(
        write_zip(files),
        filename=f"snowball-images{suffix}-{stamp}.zip",
        media_type="application/zip",
    )
