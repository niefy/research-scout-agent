from __future__ import annotations

import asyncio
import logging

from app.db.session import async_session_factory, close_db, init_db
from app.services.analysis import analyze_pending
from app.services.ingest import crawl_channels
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


@celery_app.task(name="app.tasks.jobs.crawl_and_analyze")
def crawl_and_analyze(limit: int = 50) -> dict:
    logger.info("scheduled crawl started")
    result = asyncio.run(_crawl_and_analyze(limit))
    logger.info("scheduled crawl finished: %s", result)
    return result


@celery_app.task(name="app.tasks.jobs.analyze_pending")
def analyze_pending_task(limit: int = 100) -> dict:
    return asyncio.run(_analyze_pending(limit))
