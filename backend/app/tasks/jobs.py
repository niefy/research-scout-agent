from __future__ import annotations

import asyncio
import logging

from app.core.config import settings
from app.db.session import async_session_factory, close_db, init_db
from app.services.analysis import analyze_pending
from app.services.author_crawl import analyze_author_reports, crawl_author_targets
from app.services.digest_email import send_daily_digests
from app.services.email import EmailNotConfigured
from app.services.ingest import crawl_channels
from app.services.snapshots import snapshot_watchlist_scores
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


async def _crawl_and_analyze(limit: int) -> dict:
    await init_db()
    try:
        async with async_session_factory() as session:
            crawl_results = await crawl_channels(session, limit=limit)
            analysis = await analyze_pending(session, limit=limit * 4)
        return {"crawl": crawl_results, "analysis": analysis}
    finally:
        await close_db()


async def _analyze_pending(limit: int) -> dict:
    await init_db()
    try:
        async with async_session_factory() as session:
            return await analyze_pending(session, limit=limit)
    finally:
        await close_db()


async def _crawl_authors_and_analyze(limit: int | None) -> dict:
    if not settings.author_crawl_enabled:
        return {"skipped_reason": "author_crawl_disabled"}
    await init_db()
    try:
        async with async_session_factory() as session:
            result = await crawl_author_targets(session, limit=limit)
            analysis = await analyze_author_reports(
                session, result.get("created_report_ids", [])
            )
            pending = await analyze_pending(
                session, limit=max(1, settings.author_crawl_items_per_author * 4)
            )
        return {
            "authors": {key: value for key, value in result.items() if key != "created_report_ids"},
            "analysis": analysis,
            "pending_analysis": pending,
        }
    finally:
        await close_db()


async def _snapshot_scores() -> dict:
    await init_db()
    try:
        async with async_session_factory() as session:
            return await snapshot_watchlist_scores(session)
    finally:
        await close_db()


async def _send_digests() -> dict:
    await init_db()
    try:
        async with async_session_factory() as session:
            return await send_daily_digests(session)
    finally:
        await close_db()


@celery_app.task(name="app.tasks.jobs.crawl_and_analyze")
def crawl_and_analyze(limit: int = 50) -> dict:
    logger.info("scheduled crawl started")
    result = asyncio.run(_crawl_and_analyze(limit))
    logger.info("scheduled crawl finished: %s", result)
    return result


@celery_app.task(name="app.tasks.jobs.crawl_authors_and_analyze")
def crawl_authors_and_analyze(limit: int | None = None) -> dict:
    logger.info("scheduled author crawl started")
    result = asyncio.run(_crawl_authors_and_analyze(limit))
    logger.info("scheduled author crawl finished: %s", result)
    return result


@celery_app.task(name="app.tasks.jobs.analyze_pending")
def analyze_pending_task(limit: int = 100) -> dict:
    return asyncio.run(_analyze_pending(limit))


@celery_app.task(name="app.tasks.jobs.snapshot_scores")
def snapshot_scores_task() -> dict:
    return asyncio.run(_snapshot_scores())


@celery_app.task(name="app.tasks.jobs.send_daily_digests")
def send_daily_digests_task() -> dict:
    try:
        return asyncio.run(_send_digests())
    except EmailNotConfigured as exc:
        logger.warning("daily digest skipped: %s", exc)
        return {"skipped_reason": str(exc)}
