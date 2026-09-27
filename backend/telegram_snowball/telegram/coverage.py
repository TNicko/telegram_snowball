from __future__ import annotations

from typing import Any


async def refresh_fetch_coverage(
    conn: Any,
    peer_id: int,
    *,
    min_telegram_id: int | None = None,
) -> None:
    """Record the stored-message date window. No row means Posts is uncovered.

    ``min_telegram_id`` limits the window to the contiguous newest-down scrape so
    an isolated first-visible message does not look like full history coverage.
    """
    row = await conn.execute(
        """
        SELECT MIN(date) AS covered_after, MAX(date) AS covered_before
        FROM messages
        WHERE peer_external_id = %s
          AND (%s::int IS NULL OR telegram_message_id >= %s)
        """,
        (peer_id, min_telegram_id, min_telegram_id),
    )
    span = await row.fetchone()
    if not span or span["covered_before"] is None:
        return
    await conn.execute(
        """
        INSERT INTO peer_fetch_coverage (peer_external_id, covered_after, covered_before, updated_at)
        VALUES (%s, %s, %s, now())
        ON CONFLICT (peer_external_id) DO UPDATE SET
            covered_after = EXCLUDED.covered_after,
            covered_before = EXCLUDED.covered_before,
            updated_at = now()
        """,
        (peer_id, span["covered_after"], span["covered_before"]),
    )


async def upsert_media_coverage(
    conn: Any,
    peer_id: int,
    *,
    videos_excluded: bool = False,
    large_excluded: bool = False,
    max_media_bytes: int | None = None,
) -> None:
    """Record that a media-download pass ran for this peer (even if everything was skipped)."""
    row = await conn.execute(
        """
        SELECT MIN(date) AS covered_after, MAX(date) AS covered_before
        FROM messages
        WHERE peer_external_id = %s
        """,
        (peer_id,),
    )
    span = await row.fetchone()
    if not span or span["covered_before"] is None:
        return
    await conn.execute(
        """
        INSERT INTO peer_media_coverage (
            peer_external_id, covered_after, covered_before,
            videos_excluded, large_excluded, max_media_bytes, updated_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, now())
        ON CONFLICT (peer_external_id) DO UPDATE SET
            covered_after = EXCLUDED.covered_after,
            covered_before = EXCLUDED.covered_before,
            videos_excluded = EXCLUDED.videos_excluded,
            large_excluded = EXCLUDED.large_excluded,
            max_media_bytes = COALESCE(EXCLUDED.max_media_bytes, peer_media_coverage.max_media_bytes),
            updated_at = now()
        """,
        (peer_id, span["covered_after"], span["covered_before"], videos_excluded, large_excluded, max_media_bytes),
    )
