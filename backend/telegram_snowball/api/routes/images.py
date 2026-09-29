from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, RedirectResponse

from telegram_snowball.api.routes.dialogues import PUBLIC_PEER_COLUMNS, public_peer
from telegram_snowball.config import load_settings
from telegram_snowball.db import get_conn
from telegram_snowball.phash import is_dedupable_phash, normalize_phash_hex
from telegram_snowball.telegram.client import telegram_client
from telegram_snowball.telegram.image_files import (
    ImageUnavailable,
    clear_persisted_image,
    content_type_for_file,
    ensure_local_image,
    persist_catalog_image,
    session_busy,
    telegram_io_lock,
)
from telegram_snowball.telegram.remote_image import is_remote_image_ref, resolve_remote_image_url

router = APIRouter()

BUSY_DETAIL = "Telegram session is busy with a running job. Try again after it finishes."

_IMAGE_SORTS = {
    "peers": (
        "(COUNT(DISTINCT m.peer_external_id) > 1) DESC, "
        "(COUNT(DISTINCT m.peer_external_id) < COUNT(m.message_id)) DESC, "
        "COUNT(DISTINCT m.peer_external_id) DESC, COUNT(m.message_id) DESC, "
        "MAX(m.message_date) DESC NULLS LAST, b.phash"
    ),
    "date": (
        "MAX(m.message_date) DESC NULLS LAST, "
        "COUNT(DISTINCT m.peer_external_id) DESC, COUNT(m.message_id) DESC, b.phash"
    ),
}


def _image_order_sql(sort: str) -> str:
    return _IMAGE_SORTS.get(sort, _IMAGE_SORTS["peers"])


def _http_unavailable(exc: ImageUnavailable) -> HTTPException:
    return HTTPException(status_code=exc.status, detail=exc.detail)


def _is_persisted(row: dict[str, Any], data_dir: Path) -> bool:
    rel = row.get("canonical_path")
    if not rel:
        return False
    if is_remote_image_ref(str(rel)):
        return True
    dest = (data_dir / str(rel)).resolve()
    root = data_dir.resolve()
    if root not in dest.parents and dest != root:
        return False
    return dest.is_file()


def _public_image(
    row: dict[str, Any],
    *,
    peers: list[dict[str, Any]],
    data_dir: Path,
) -> dict[str, Any]:
    phash = row["phash"]
    return {
        "phash": phash,
        "file_url": f"/api/images/{phash}/file",
        "appearances": int(row["appearances"] or 0),
        "unique_peers": int(row["unique_peers"] or 0),
        "last_seen_at": row["last_seen_at"],
        "refcount": int(row["refcount"] or 0),
        "persisted": _is_persisted(row, data_dir),
        "peers": peers,
    }


async def _require_blob(conn: Any, phash: str) -> None:
    row = await conn.execute("SELECT 1 FROM image_blobs WHERE phash = %s", (phash,))
    if await row.fetchone() is None:
        raise HTTPException(status_code=404, detail="Image not found")


async def _attach_image_peers(
    conn: Any,
    items: list[dict[str, Any]],
    *,
    data_dir: Path,
) -> list[dict[str, Any]]:
    phashes = [str(row["phash"]) for row in items]
    grouped: dict[str, list[dict[str, Any]]] = {phash: [] for phash in phashes}
    if not phashes:
        return [_public_image(row, peers=[], data_dir=data_dir) for row in items]
    fan = await conn.execute(
        """
        SELECT
            ibm.phash,
            ibm.peer_external_id,
            COUNT(*) AS appearances,
            COUNT(*) FILTER (WHERE msg.fwd_from IS NOT NULL) AS forwarded,
            MAX(ibm.message_date) AS last_seen_at
        FROM image_blob_messages ibm
        JOIN messages msg ON msg.id = ibm.message_id
        WHERE ibm.phash = ANY(%s)
        GROUP BY ibm.phash, ibm.peer_external_id
        ORDER BY appearances DESC, last_seen_at DESC NULLS LAST, ibm.peer_external_id
        """,
        (phashes,),
    )
    fan_rows = await fan.fetchall()
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
        grouped.setdefault(str(row["phash"]), []).append(
            {
                "peer": peer,
                "appearances": int(row["appearances"] or 0),
                "forwarded": int(row["forwarded"] or 0),
            }
        )
    return [
        _public_image(row, peers=grouped.get(str(row["phash"]), []), data_dir=data_dir)
        for row in items
    ]


@router.get("/images")
async def list_images(
    peer_external_id: int | None = None,
    sort: Literal["peers", "date"] = Query(default="peers"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    order_sql = _image_order_sql(sort)
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
                """
                SELECT COUNT(DISTINCT ibm.phash) AS n
                FROM image_blob_messages ibm
                WHERE ibm.peer_external_id = %s
                """,
                (peer_external_id,),
            )
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
                WHERE EXISTS (
                    SELECT 1
                    FROM image_blob_messages hit
                    WHERE hit.phash = b.phash
                      AND hit.peer_external_id = %s
                )
                GROUP BY b.phash, b.canonical_path, b.refcount
                ORDER BY {order_sql}
                LIMIT %s OFFSET %s
                """,
                (peer_external_id, limit, offset),
            )
        else:
            count_row = await conn.execute("SELECT COUNT(*) AS n FROM image_blobs")
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
                GROUP BY b.phash, b.canonical_path, b.refcount
                ORDER BY {order_sql}
                LIMIT %s OFFSET %s
                """,
                (limit, offset),
            )
        total = int((await count_row.fetchone())["n"])
        items = [dict(row) for row in await rows.fetchall()]
        images = await _attach_image_peers(conn, items, data_dir=settings.data_dir)
    return {
        "images": images,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/images/{phash}/file", response_model=None)
async def image_file(phash: str) -> FileResponse | RedirectResponse:
    normalized = normalize_phash_hex(phash)
    if not is_dedupable_phash(normalized):
        raise HTTPException(status_code=404, detail="Image not found")
    settings = load_settings()
    async with get_conn(settings) as conn:
        await _require_blob(conn, normalized)
        path_row = await conn.execute(
            "SELECT canonical_path FROM image_blobs WHERE phash = %s",
            (normalized,),
        )
        stored = await path_row.fetchone()
        canonical = str((stored or {}).get("canonical_path") or "")
        if is_remote_image_ref(canonical):
            try:
                url = resolve_remote_image_url(canonical)
            except Exception as exc:
                raise HTTPException(status_code=503, detail=str(exc)) from exc
            return RedirectResponse(
                url,
                status_code=302,
                headers={"Cache-Control": "private, max-age=300"},
            )
        try:
            dest = await ensure_local_image(conn, settings, normalized, allow_telegram=False)
        except ImageUnavailable:
            dest = None
        if dest is None:
            if await session_busy(conn):
                raise HTTPException(status_code=409, detail=BUSY_DETAIL)
            async with telegram_io_lock:
                try:
                    dest = await ensure_local_image(
                        conn, settings, normalized, allow_telegram=False
                    )
                except ImageUnavailable:
                    dest = None
                if dest is None:
                    try:
                        async with telegram_client(settings) as client:
                            dest = await ensure_local_image(
                                conn,
                                settings,
                                normalized,
                                allow_telegram=True,
                                client=client,
                            )
                    except ImageUnavailable as exc:
                        raise _http_unavailable(exc) from exc
                    except Exception as exc:
                        raise HTTPException(
                            status_code=503,
                            detail=f"Could not load image from Telegram: {exc}",
                        ) from exc
        await conn.commit()
    return FileResponse(
        dest,
        media_type=content_type_for_file(dest),
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )


@router.post("/images/{phash}/persist")
async def persist_image(phash: str) -> dict[str, Any]:
    normalized = normalize_phash_hex(phash)
    if not is_dedupable_phash(normalized):
        raise HTTPException(status_code=404, detail="Image not found")
    settings = load_settings()
    async with get_conn(settings) as conn:
        await _require_blob(conn, normalized)
        try:
            await persist_catalog_image(conn, settings, normalized, allow_telegram=False)
        except ImageUnavailable:
            if await session_busy(conn):
                raise HTTPException(status_code=409, detail=BUSY_DETAIL)
            async with telegram_io_lock:
                try:
                    await persist_catalog_image(
                        conn, settings, normalized, allow_telegram=False
                    )
                except ImageUnavailable:
                    try:
                        async with telegram_client(settings) as client:
                            await persist_catalog_image(
                                conn,
                                settings,
                                normalized,
                                allow_telegram=True,
                                client=client,
                            )
                    except ImageUnavailable as exc:
                        raise _http_unavailable(exc) from exc
                    except Exception as exc:
                        raise HTTPException(
                            status_code=503,
                            detail=f"Could not download image from Telegram: {exc}",
                        ) from exc
        await conn.commit()
    return {
        "phash": normalized,
        "persisted": True,
        "file_url": f"/api/images/{normalized}/file",
    }


@router.delete("/images/{phash}/persist")
async def unpersist_image(phash: str) -> dict[str, Any]:
    normalized = normalize_phash_hex(phash)
    if not is_dedupable_phash(normalized):
        raise HTTPException(status_code=404, detail="Image not found")
    settings = load_settings()
    async with get_conn(settings) as conn:
        await _require_blob(conn, normalized)
        try:
            await clear_persisted_image(conn, settings, normalized)
        except ImageUnavailable as exc:
            raise _http_unavailable(exc) from exc
        await conn.commit()
    return {
        "phash": normalized,
        "persisted": False,
        "file_url": f"/api/images/{normalized}/file",
    }
