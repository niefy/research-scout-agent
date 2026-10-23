from __future__ import annotations

from datetime import date
from typing import Literal

from fastapi import APIRouter, Query

from app.api.deps import DB, CurrentUser
from app.schemas.digest import DigestResponse
from app.schemas.stock import ScoreScope
from app.services.digest import build_digest

router = APIRouter(tags=["digest"])

Window = Literal["7d", "30d", "90d", "all"]


@router.get("/digest", response_model=DigestResponse)
async def get_digest(
    session: DB,
    user: CurrentUser,
    digest_date: date | None = Query(default=None, alias="date"),
    scope: ScoreScope | None = None,
    window: Window = "30d",
) -> DigestResponse:
    data = await build_digest(
        session,
        user,
        scope=scope,
        window=window,
        digest_date=digest_date,
    )
    return DigestResponse(**data)


__all__ = ["router"]
