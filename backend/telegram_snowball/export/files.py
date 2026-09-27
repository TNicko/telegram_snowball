from __future__ import annotations

import csv
import io
import json
import zipfile
from datetime import date, datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any
from uuid import UUID

from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from telegram_snowball.jsonutil import json_safe


def export_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def csv_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (list, dict)):
        return json.dumps(json_safe(value), ensure_ascii=False, separators=(",", ":"))
    return str(value)


def write_csv(rows: list[dict[str, Any]], columns: list[str]) -> bytes:
    buf = io.StringIO()
    writer = csv.DictWriter(
        buf,
        fieldnames=columns,
        extrasaction="ignore",
        lineterminator="\n",
        quoting=csv.QUOTE_MINIMAL,
    )
    writer.writeheader()
    for row in rows:
        writer.writerow({key: csv_cell(row.get(key)) for key in columns})
    return buf.getvalue().encode("utf-8-sig")


def write_json(payload: Any) -> bytes:
    return json.dumps(json_safe(payload), ensure_ascii=False, indent=2).encode("utf-8")


def write_zip(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in files.items():
            if not data:
                continue
            archive.writestr(name, data)
    return buf.getvalue()


def download_response(data: bytes, *, filename: str, media_type: str) -> FileResponse:
    tmp = NamedTemporaryFile(delete=False, suffix=Path(filename).suffix)
    tmp.write(data)
    tmp.close()
    return FileResponse(
        tmp.name,
        media_type=media_type,
        filename=filename,
        background=BackgroundTask(Path(tmp.name).unlink, missing_ok=True),
    )
