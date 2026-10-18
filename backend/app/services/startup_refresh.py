from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import async_session_factory
from app.models.job import IngestRun
from app.services.analysis import analyze_pending
from app.services.ingest import crawl_channels

logger = logging.getLogger(__name__)


async def last_successful_crawl_at(session: AsyncSession) -> datetime | None:
    """Return the finish time of the most recent successful crawl run."""
    return await session.scalar(
        select(func.max(IngestRun.finished_at)).where(
            IngestRun.run_type == "crawl",
            IngestRun.status == "success",
            IngestRun.finished_at.is_not(None),
        )
    )


async def is_crawl_running(session: AsyncSession, *, since: datetime) -> bool:
    """Whether another crawl started after ``since`` and has not finished."""
    run_id = await session.scalar(
        select(IngestRun.id)
        .where(
            IngestRun.run_type == "crawl",
            IngestRun.status == "running",
            IngestRun.started_at >= since,
        )
        .limit(1)
    )
    return run_id is not None


async def refresh_if_stale() -> dict[str, Any]:
    """Crawl immediately unless a successful crawl happened recently.

    Runs as a background task during application startup. The check and crawl
    are deliberately kept outside the request path so a slow source can never
    block health checks or the first page load.
    """
    stale_after = timedelta(minutes=max(1, settings.startup_refresh_stale_minutes))
    now = datetime.now(UTC)

    async with async_session_factory() as session:
        last_crawl_at = await last_successful_crawl_at(session)
        running = await is_crawl_running(session, since=now - stale_after)

    if running:
        logger.info(
            "startup refresh skipped: another crawl started within %s minutes",
            settings.startup_refresh_stale_minutes,
        )
        return {"skipped": True, "reason": "crawl_in_progress"}

    if last_crawl_at is not None:
        age = now - last_crawl_at
        if age < stale_after:
            logger.info(
                "startup refresh skipped: last successful crawl at %s (%.1f minutes ago)",
                last_crawl_at.isoformat(),
                age.total_seconds() / 60,
            )
            return {
                "skipped": True,
                "reason": "fresh",
                "last_crawl_at": last_crawl_at.isoformat(),
                "age_minutes": round(age.total_seconds() / 60, 1),
            }

    logger.info(
        "startup refresh started: last successful crawl=%s",
        last_crawl_at.isoformat() if last_crawl_at else "never",
    )
    try:
        async with async_session_factory() as session:
            crawl_results = await crawl_channels(session)
            analysis = await analyze_pending(
                session,
                limit=max(1, settings.crawl_max_items_per_channel * 4),
            )
    except Exception as exc:  # noqa: BLE001 - a background refresh must not crash the app
        logger.exception("startup refresh failed")
        return {"skipped": False, "error": str(exc)[:500]}

    result = {"skipped": False, "crawl": crawl_results, "analysis": analysis}
    logger.info("startup refresh finished: %s", result)
    return result
