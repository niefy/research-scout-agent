from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import admin, auth, authors, digest, feed, health, watchlist
from app.core.config import settings
from app.db.session import async_session_factory, close_db, init_db
from app.services.seed import seed_base, seed_demo
from app.services.startup_refresh import refresh_if_stale

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.auto_create_tables:
        await init_db()
    if settings.seed_on_startup:
        async with async_session_factory() as session:
            summary = await seed_base(session)
            logger.info("bootstrap seed: %s", summary)
            if settings.seed_demo_data:
                demo = await seed_demo(session)
                logger.info("demo data: %s", demo)

    refresh_task: asyncio.Task | None = None
    if settings.startup_refresh_enabled:
        # Fire-and-forget: don't delay startup or the first request. The task
        # itself decides whether the last successful crawl is still fresh.
        refresh_task = asyncio.create_task(refresh_if_stale(), name="startup-refresh")
        app.state.startup_refresh_task = refresh_task
        logger.info(
            "startup refresh scheduled (skip if crawled within %s minutes)",
            settings.startup_refresh_stale_minutes,
        )

    try:
        yield
    finally:
        if refresh_task is not None and not refresh_task.done():
            refresh_task.cancel()
            try:
                await refresh_task
            except asyncio.CancelledError:
                pass
            except Exception:  # noqa: BLE001 - shutdown must not mask the original exit
                logger.exception("startup refresh task failed during shutdown")
        await close_db()


def create_app() -> FastAPI:
    application = FastAPI(
        title=settings.app_name,
        description="Research Scout - financial research report scoring and aggregation",
        version="0.1.0",
        lifespan=lifespan,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    api_prefix = "/api/v1"
    application.include_router(health.router, prefix=api_prefix)
    application.include_router(auth.router, prefix=api_prefix)
    application.include_router(authors.router, prefix=api_prefix)
    application.include_router(feed.router, prefix=api_prefix)
    application.include_router(digest.router, prefix=api_prefix)
    application.include_router(watchlist.router, prefix=api_prefix)
    application.include_router(admin.router, prefix=api_prefix)

    @application.get("/health", tags=["health"])
    async def root_health() -> dict:
        return {"status": "ok", "service": settings.app_name}

    @application.get("/", tags=["meta"])
    async def root() -> dict:
        return {
            "service": settings.app_name,
            "version": "0.1.0",
            "docs": "/docs",
            "api": api_prefix,
        }

    return application


app = create_app()
