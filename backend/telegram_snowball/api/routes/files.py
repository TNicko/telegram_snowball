from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from telegram_snowball.api.routes.dialogues import PUBLIC_PEER_COLUMNS, public_peer
from telegram_snowball.bytesfmt import format_bytes
from telegram_snowball.catalog import stored_kind_is
from telegram_snowball.config import load_settings
from telegram_snowball.db import get_conn
from telegram_snowball.telegram.client import telegram_client
from telegram_snowball.telegram.file_files import (
    FileUnavailable,
    content_type_for_file,
    fetch_file_from_telegram,
    file_catalog_url,
    lookup_file_sources,
    parse_file_id,
    persisted_file_path,
    safe_filename,
)
from telegram_snowball.telegram.image_files import session_busy, telegram_io_lock

router = APIRouter()

BUSY_DETAIL = "Telegram session is busy with a running job. Try again after it finishes."

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


def _http_unavailable(exc: FileUnavailable) -> HTTPException:
    return HTTPException(status_code=exc.status, detail=exc.detail)


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _public_file(row: dict[str, Any], *, peers: list[dict[str, Any]]) -> dict[str, Any]:
    file_id = str(row["file_id"])
    size_bytes = _int_or_none(row.get("size_bytes"))
    return {
        "id": file_id,
        "file_url": file_catalog_url(file_id),
        "size_bytes": size_bytes,
        "size_label": format_bytes(size_bytes),
        "mime_type": row.get("mime_type"),
        "file_name": row.get("file_name"),
        "appearances": int(row["appearances"] or 0),
        "unique_peers": int(row["unique_peers"] or 0),
        "last_seen_at": row["last_seen_at"],
        "persisted": bool(row.get("persisted")),
        "peers": peers,
    }


async def _attach_file_peers(
    conn: Any,
    items: list[dict[str, Any]],
    *,
    data_dir: Path,
) -> list[dict[str, Any]]:
    ids = [str(row["file_id"]) for row in items]
    grouped: dict[str, list[dict[str, Any]]] = {file_id: [] for file_id in ids}
    if not ids:
        return [_public_file(row, peers=[]) for row in items]
    doc_ids = [file_id for file_id in ids if not file_id.startswith("msg:")]
    msg_ids = [file_id[4:] for file_id in ids if file_id.startswith("msg:")]
    fan_rows: list[Any] = []
    if doc_ids:
        fan = await conn.execute(
            f"""
            SELECT
                media->>'document_id' AS file_id,
                peer_external_id,
                COUNT(*) AS appearances,
                COUNT(*) FILTER (WHERE fwd_from IS NOT NULL) AS forwarded,
                MAX(date) AS last_seen_at
            FROM messages
            WHERE {stored_kind_is("document")}
              AND media->>'document_id' = ANY(%s)
            GROUP BY media->>'document_id', peer_external_id
            ORDER BY appearances DESC, last_seen_at DESC NULLS LAST, peer_external_id
            """,
            (doc_ids,),
        )
        fan_rows.extend(await fan.fetchall())
    if msg_ids:
        fan = await conn.execute(
            f"""
            SELECT
                'msg:' || id::text AS file_id,
                peer_external_id,
                1 AS appearances,
                CASE WHEN fwd_from IS NOT NULL THEN 1 ELSE 0 END AS forwarded,
                date AS last_seen_at
            FROM messages
            WHERE id = ANY(%s::uuid[])
              AND {stored_kind_is("document")}
            """,
            (msg_ids,),
        )
        fan_rows.extend(await fan.fetchall())
    peer_ids = sorted({int(row["peer_external_id"]) for row in fan_rows})
    by_id: dict[int, dict[str, Any]] = {}
    if peer_ids:
        found = await conn.execute(
            f"SELECT {PUBLIC_PEER_COLUMNS} FROM peers WHERE external_id = ANY(%s)",
            (peer_ids,),
        )
        for row in await found.fetchall():
            peer = public_peer(dict(row), data_dir=data_dir)
            by_id[int(peer["external_id"])] = peer
    for row in fan_rows:
        peer = by_id.get(int(row["peer_external_id"]))
        if peer is None:
            continue
        grouped.setdefault(str(row["file_id"]), []).append(
            {
                "peer": peer,
                "appearances": int(row["appearances"] or 0),
                "forwarded": int(row["forwarded"] or 0),
            }
        )
    return [_public_file(row, peers=grouped.get(str(row["file_id"]), [])) for row in items]


@router.get("/files")
async def list_files(
    peer_external_id: int | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    settings = load_settings()
    async with get_conn(settings) as conn:
        if peer_external_id is not None:
            exists = await conn.execute(
                "SELECT 1 FROM peers WHERE external_id = %s",
                (peer_external_id,),
            )
            if await exists.fetchone() is None:
                raise HTTPException(status_code=404, detail="Peer not found")
            count_row = await conn.execute(
                f"""
                SELECT COUNT(*) AS n FROM (
                    SELECT COALESCE(NULLIF(media->>'document_id', ''), 'msg:' || id::text) AS file_id
                    FROM messages
                    WHERE {stored_kind_is("document")}
                      AND peer_external_id = %s
                    GROUP BY 1
                ) t
                """,
                (peer_external_id,),
            )
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
                LIMIT %s OFFSET %s
                """,
                (peer_external_id, limit, offset),
            )
        else:
            count_row = await conn.execute(
                f"""
                SELECT COUNT(*) AS n FROM (
                    SELECT COALESCE(NULLIF(media->>'document_id', ''), 'msg:' || id::text) AS file_id
                    FROM messages
                    WHERE {stored_kind_is("document")}
                    GROUP BY 1
                ) t
                """
            )
            rows = await conn.execute(
                f"""
                SELECT {_FILE_SELECT}
                FROM messages
                WHERE {stored_kind_is("document")}
                GROUP BY 1
                ORDER BY last_seen_at DESC NULLS LAST, file_id
                LIMIT %s OFFSET %s
                """,
                (limit, offset),
            )
        total = int((await count_row.fetchone())["n"])
        items = [dict(row) for row in await rows.fetchall()]
        files = await _attach_file_peers(conn, items, data_dir=settings.data_dir)
    return {
        "files": files,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


async def _serve_catalog_file(file_id: str) -> FileResponse:
    try:
        kind, ident = parse_file_id(file_id)
    except FileUnavailable as exc:
        raise _http_unavailable(exc) from exc
    settings = load_settings()
    async with get_conn(settings) as conn:
        sources = await lookup_file_sources(conn, kind=kind, ident=ident)
        if not sources:
            raise HTTPException(status_code=404, detail="File not found")
        media = sources[0].get("media") if isinstance(sources[0].get("media"), dict) else {}
        filename = safe_filename(
            str(media.get("file_name") or "") if isinstance(media, dict) else None,
            mime=str(media.get("mime_type") or "") if isinstance(media, dict) else None,
        )
        local = None
        for row in sources:
            local = persisted_file_path(
                settings, row.get("media") if isinstance(row.get("media"), dict) else None
            )
            if local is not None:
                break
        if local is not None:
            mime = str(media.get("mime_type") or "") if isinstance(media, dict) else None
            return FileResponse(
                local,
                media_type=content_type_for_file(mime, local),
                filename=filename,
                content_disposition_type="attachment",
            )
        if await session_busy(conn):
            raise HTTPException(status_code=409, detail=BUSY_DETAIL)
        async with telegram_io_lock:
            for row in sources:
                local = persisted_file_path(
                    settings, row.get("media") if isinstance(row.get("media"), dict) else None
                )
                if local is not None:
                    mime = str(media.get("mime_type") or "") if isinstance(media, dict) else None
                    return FileResponse(
                        local,
                        media_type=content_type_for_file(mime, local),
                        filename=filename,
                        content_disposition_type="attachment",
                    )
            try:
                async with telegram_client(settings) as client:
                    dest, filename, mime = await fetch_file_from_telegram(
                        client,
                        conn,
                        settings,
                        kind=kind,
                        ident=ident,
                    )
            except FileUnavailable as exc:
                raise _http_unavailable(exc) from exc
            except Exception as exc:
                raise HTTPException(
                    status_code=503,
                    detail=f"Could not download file from Telegram: {exc}",
                ) from exc
            await conn.commit()
            return FileResponse(
                dest,
                media_type=mime,
                filename=filename,
                content_disposition_type="attachment",
                background=BackgroundTask(dest.unlink, missing_ok=True),
            )


@router.get("/files/msg/{message_id}/file")
async def file_by_message(message_id: UUID) -> FileResponse:
    return await _serve_catalog_file(f"msg:{message_id}")


@router.get("/files/{document_id}/file")
async def file_by_document(document_id: str) -> FileResponse:
    return await _serve_catalog_file(document_id)
