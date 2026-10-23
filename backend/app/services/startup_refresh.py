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
from app.services.author_crawl import analyze_author_reports, crawl_author_targets
from app.services.ingest import crawl_channels

logger = logging.getLogger(__name__)


async def last_successful_crawl_at(session: AsyncSession) -> datetime | None:
    """Return the finish time of the most recent successful channel crawl."""
    return await session.scalar(
        select(func.max(IngestRun.finished_at)).where(
            IngestRun.run_type == "crawl",
            IngestRun.status == "success",
            IngestRun.finished_at.is_not(None),
        )
    )


async def is_crawl_running(session: AsyncSession, *, since: datetime) -> bool:
    """Whether another channel crawl started after ``since`` and has not finished."""
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


async def last_successful_author_crawl_at(session: AsyncSession) -> datetime | None:
    return await session.scalar(
        select(func.max(IngestRun.finished_at)).where(
            IngestRun.run_type == "author_crawl",
            IngestRun.status == "success",
            IngestRun.finished_at.is_not(None),
        )
    )


async def is_author_crawl_running(session: AsyncSession, *, since: datetime) -> bool:
    run_id = await session.scalar(
        select(IngestRun.id)
        .where(
            IngestRun.run_type == "author_crawl",
            IngestRun.status == "running",
            IngestRun.started_at >= since,
        )
        .limit(1)
    )
    return run_id is not None


def _is_due(
    last_run_at: datetime | None,
    running: bool,
    now: datetime,
    stale_after: timedelta,
) -> bool:
    if running:
        return False
    if last_run_at is None:
        return True
    return now - last_run_at >= stale_after


def _freshness(last_run_at: datetime | None, now: datetime) -> dict[str, Any]:
    if last_run_at is None:
        return {"last_run_at": None, "age_minutes": None}
    return {
        "last_run_at": last_run_at.isoformat(),
        "age_minutes": round((now - last_run_at).total_seconds() / 60, 1),
    }


async def refresh_if_stale() -> dict[str, Any]:
    """Refresh channel and author feeds unless they were crawled recently.

    Runs as a background task during application startup. Channel crawls and
    author timeline crawls have independent freshness windows so a broken
    channel never blocks author backfills.
    """
    stale_after = timedelta(minutes=max(1, settings.startup_refresh_stale_minutes))
    now = datetime.now(UTC)

    async with async_session_factory() as session:
        last_channel_at = await last_successful_crawl_at(session)
        channel_running = await is_crawl_running(session, since=now - stale_after)
        last_author_at = await last_successful_author_crawl_at(session)
        author_running = await is_author_crawl_running(session, since=now - stale_after)

    channel_due = _is_due(last_channel_at, channel_running, now, stale_after)
    author_due = settings.author_crawl_enabled and _is_due(
        last_author_at, author_running, now, stale_after
    )

    if not channel_due and not author_due:
        reason = (
            "crawl_in_progress"
            if channel_running or author_running
            else "fresh"
        )
        logger.info("startup refresh skipped: %s", reason)
        return {
            "skipped": True,
            "reason": reason,
            "channels": _freshness(last_channel_at, now),
            "authors": _freshness(last_author_at, now),
        }

    logger.info(
        "startup refresh started: channels_due=%s authors_due=%s",
        channel_due,
        author_due,
    )
    try:
        async with async_session_factory() as session:
            crawl_results: list[dict] = []
            author_result: dict | None = None
            author_analysis: dict | None = None
            if channel_due:
                crawl_results = await crawl_channels(session)
            if author_due:
                author_result = await crawl_author_targets(session)
                author_analysis = await analyze_author_reports(
                    session, author_result.get("created_report_ids", [])
                )
            channel_limit = max(1, settings.crawl_max_items_per_channel * 4)
            analysis = await analyze_pending(
                session,
                limit=max(channel_limit, settings.author_crawl_items_per_author * 4),
            )
    except Exception as exc:  # noqa: BLE001 - a background refresh must not crash the app
        logger.exception("startup refresh failed")
        return {"skipped": False, "error": str(exc)[:500]}

    result = {
        "skipped": False,
        "channels_due": channel_due,
        "authors_due": author_due,
        "channels": crawl_results,
        "authors": author_result,
        "author_analysis": author_analysis,
        "analysis": analysis,
        # Backwards-compatible alias for callers that only knew channel crawls.
        "crawl": crawl_results,
    }
    logger.info("startup refresh finished: %s", result)
    return result
