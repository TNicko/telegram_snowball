from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from telegram_snowball.config import load_settings
from telegram_snowball.db import get_conn
from telegram_snowball.export.file_catalog import export_catalog_files
from telegram_snowball.export.images import export_images
from telegram_snowball.export.messages import export_messages
from telegram_snowball.export.peers import PEER_TYPES, export_peers
from telegram_snowball.export.videos import export_videos

router = APIRouter()

ExportFormat = Literal["csv", "json"]


class PeersExportIn(BaseModel):
    format: ExportFormat = "csv"
    peer_types: list[str] | None = None
    include_forward_edges: bool = True


class MessagesExportIn(BaseModel):
    format: ExportFormat = "json"
    peer_external_id: int | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
    text_only: bool = False
    media_only: bool = False
    include_forwards: bool = True


class ImagesExportIn(BaseModel):
    format: ExportFormat = "csv"
    peer_external_id: int | None = None


class VideosExportIn(BaseModel):
    format: ExportFormat = "csv"
    peer_external_id: int | None = None


class FilesExportIn(BaseModel):
    format: ExportFormat = "csv"
    peer_external_id: int | None = None


async def _require_peer(conn: Any, peer_external_id: int | None) -> None:
    if peer_external_id is None:
        return
    found = await conn.execute("SELECT 1 FROM peers WHERE external_id = %s", (peer_external_id,))
    if await found.fetchone() is None:
        raise HTTPException(status_code=404, detail="Peer not found")


@router.post("/export/peers")
async def export_peers_route(body: PeersExportIn):
    if body.peer_types:
        unknown = [item for item in body.peer_types if item not in PEER_TYPES]
        if unknown:
            raise HTTPException(status_code=400, detail=f"Unknown peer types: {', '.join(unknown)}")
    settings = load_settings()
    async with get_conn(settings) as conn:
        return await export_peers(
            conn,
            fmt=body.format,
            peer_types=body.peer_types,
            include_forward_edges=body.include_forward_edges,
        )


@router.post("/export/messages")
async def export_messages_route(body: MessagesExportIn):
    settings = load_settings()
    async with get_conn(settings) as conn:
        await _require_peer(conn, body.peer_external_id)
        return await export_messages(
            conn,
            fmt=body.format,
            peer_external_id=body.peer_external_id,
            date_from=body.date_from,
            date_to=body.date_to,
            text_only=body.text_only,
            media_only=body.media_only,
            include_forwards=body.include_forwards,
        )


@router.post("/export/images")
async def export_images_route(body: ImagesExportIn):
    settings = load_settings()
    async with get_conn(settings) as conn:
        await _require_peer(conn, body.peer_external_id)
        return await export_images(
            conn,
            fmt=body.format,
            peer_external_id=body.peer_external_id,
        )


@router.post("/export/videos")
async def export_videos_route(body: VideosExportIn):
    settings = load_settings()
    async with get_conn(settings) as conn:
        await _require_peer(conn, body.peer_external_id)
        return await export_videos(
            conn,
            fmt=body.format,
            peer_external_id=body.peer_external_id,
        )


@router.post("/export/files")
async def export_files_route(body: FilesExportIn):
    settings = load_settings()
    async with get_conn(settings) as conn:
        await _require_peer(conn, body.peer_external_id)
        return await export_catalog_files(
            conn,
            fmt=body.format,
            peer_external_id=body.peer_external_id,
        )
