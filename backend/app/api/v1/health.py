from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import text

from app.api.deps import DB
from app.core.config import settings

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "service": settings.app_name,
        "environment": settings.environment,
        "llm_mode": "live" if settings.llm_enabled else "mock",
    }


@router.get("/health/ready")
async def readiness(session: DB) -> dict:
    await session.execute(text("SELECT 1"))
    return {"status": "ready"}
