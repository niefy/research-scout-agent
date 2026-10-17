from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import DB, CurrentUser
from app.schemas.report import (
    FeedResponse,
    InteractionIn,
    InteractionOut,
    ReportDetail,
)
from app.services import feed as feed_service

router = APIRouter(tags=["feed"])


@router.get("/feed", response_model=FeedResponse)
async def get_feed(
    session: DB,
    user: CurrentUser,
    scope: Literal["following", "discover"] = "following",
    sort: Literal["time", "smart", "hot", "latest"] | None = None,
    window: Literal["24h", "72h", "7d", "30d", "all"] | None = None,
    category: Literal["stock", "industry", "macro"] | None = None,
    stock_code: str | None = Query(default=None, max_length=32),
    limit: int = Query(default=20, ge=1, le=50),
    cursor: str | None = None,
) -> FeedResponse:
    resolved_sort = sort or ("smart" if scope == "following" else "hot")
    options = feed_service.FeedOptions(
        scope=scope,
        sort=resolved_sort,
        window=window,
        category=category,
        stock_code=stock_code,
        limit=limit,
        cursor=cursor,
    )
    data = await feed_service.get_feed(session, user.id, options)
    return FeedResponse(**data)


@router.get("/reports/{report_id}", response_model=ReportDetail)
async def get_report(report_id: int, session: DB, user: CurrentUser) -> ReportDetail:
    data = await feed_service.get_report_detail(session, report_id, user.id)
    if data is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="report not found")
    return ReportDetail(**data)


@router.post("/reports/{report_id}/interaction", response_model=InteractionOut)
async def interact(
    report_id: int,
    payload: InteractionIn,
    session: DB,
    user: CurrentUser,
) -> InteractionOut:
    interaction = await feed_service.set_interaction(
        session,
        user.id,
        report_id,
        saved=payload.saved,
        hidden=payload.hidden,
        read=payload.read,
    )
    return InteractionOut(
        report_id=interaction.report_id,
        saved=interaction.saved,
        hidden=interaction.hidden,
        read_at=interaction.read_at,
    )
