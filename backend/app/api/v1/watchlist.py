from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import DB, CurrentUser
from app.models.report import Report
from app.schemas.common import Message
from app.schemas.stock import (
    FeedbackIn,
    FeedbackOut,
    ScoreScope,
    SecurityOut,
    StockDetailOut,
    StockHistoryOut,
    StockHistoryPointOut,
    StockScoreOut,
    WatchlistAdd,
    WatchlistItemOut,
    WatchlistUpdate,
)
from app.services import feedback as feedback_service
from app.services import stocks as stock_service
from app.services.snapshots import history_deltas, list_score_history

router = APIRouter(tags=["stocks"])

Window = Literal["7d", "30d", "90d", "all"]


@router.get("/securities/search", response_model=list[SecurityOut])
async def search_securities(
    session: DB,
    user: CurrentUser,
    q: str = Query(min_length=1, max_length=32),
    limit: int = Query(default=20, ge=1, le=50),
) -> list[SecurityOut]:
    rows = await stock_service.search_securities(session, q, limit=limit)
    return [SecurityOut.model_validate(row) for row in rows]


@router.get("/watchlist", response_model=list[WatchlistItemOut])
async def list_watchlist(
    session: DB,
    user: CurrentUser,
    scope: ScoreScope | None = None,
    window: Window = "30d",
) -> list[WatchlistItemOut]:
    items = await stock_service.list_watchlist(
        session, user.id, scope=scope, window=window
    )
    return [WatchlistItemOut(**item) for item in items]


@router.post("/watchlist", response_model=WatchlistItemOut, status_code=status.HTTP_201_CREATED)
async def add_watchlist(
    payload: WatchlistAdd,
    session: DB,
    user: CurrentUser,
) -> WatchlistItemOut:
    if payload.security_id is None and not payload.code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="security_id or code is required",
        )
    try:
        item, security = await stock_service.add_watchlist_item(
            session,
            user.id,
            security_id=payload.security_id,
            code=payload.code,
            note=payload.note,
        )
    except stock_service.StockNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except stock_service.WatchlistDuplicateError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    score = await stock_service.compute_stock_score(
        session,
        user.id,
        security,
        scope=stock_service.normalize_scope(None, user),
    )
    return WatchlistItemOut(
        id=item.id,
        security=SecurityOut.model_validate(security),
        note=item.note,
        sort_order=item.sort_order,
        score=StockScoreOut(**stock_service.serialize_stock_score(score)),
        added_at=item.created_at,
    )


@router.patch("/watchlist/{security_id}", response_model=Message)
async def update_watchlist(
    security_id: int,
    payload: WatchlistUpdate,
    session: DB,
    user: CurrentUser,
) -> Message:
    item = await stock_service.update_watchlist_item(
        session,
        user.id,
        security_id,
        note=payload.note,
        sort_order=payload.sort_order,
    )
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="item not found")
    return Message(message="updated")


@router.delete("/watchlist/{security_id}", response_model=Message)
async def remove_watchlist(
    security_id: int,
    session: DB,
    user: CurrentUser,
) -> Message:
    removed = await stock_service.remove_watchlist_item(session, user.id, security_id)
    if not removed:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="item not found")
    return Message(message="removed")


@router.get("/stocks/{code}", response_model=StockDetailOut)
async def stock_detail(
    code: str,
    session: DB,
    user: CurrentUser,
    scope: ScoreScope | None = None,
    window: Window = "30d",
    limit: int = Query(default=20, ge=1, le=50),
) -> StockDetailOut:
    data = await stock_service.stock_detail(
        session,
        user.id,
        code,
        scope=scope,
        window=window,
        limit=limit,
        use_llm_conclusion=True,
    )
    if data is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="security not found")
    return StockDetailOut(**data)


@router.get("/stocks/{code}/score", response_model=StockScoreOut)
async def stock_score(
    code: str,
    session: DB,
    user: CurrentUser,
    scope: ScoreScope | None = None,
    window: Window = "30d",
) -> StockScoreOut:
    security = await stock_service.get_security(session, code)
    if security is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="security not found")
    score = await stock_service.compute_stock_score(
        session, user.id, security, scope=scope, window=window
    )
    return StockScoreOut(**stock_service.serialize_stock_score(score))


@router.get("/stocks/{code}/history", response_model=StockHistoryOut)
async def stock_history(
    code: str,
    session: DB,
    user: CurrentUser,
    scope: ScoreScope | None = None,
    window: Window = "30d",
    days: int = Query(default=30, ge=1, le=365),
) -> StockHistoryOut:
    security = await stock_service.get_security(session, code)
    if security is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="security not found"
        )
    resolved_scope = stock_service.normalize_scope(scope, user)
    snapshots = await list_score_history(
        session,
        user.id,
        security.id,
        scope=resolved_scope,
        window=window,
        days=days,
    )
    return StockHistoryOut(
        security=SecurityOut.model_validate(security),
        scope=resolved_scope,
        window=window,
        points=[
            StockHistoryPointOut(
                computed_at=snapshot.computed_at,
                total_points=snapshot.total_points,
                display_score=(
                    snapshot.total_points
                    if snapshot.evidence_level != "none"
                    else None
                ),
                evidence_level=snapshot.evidence_level,
                report_count=snapshot.report_count,
                relation_counts=snapshot.relation_counts or {},
            )
            for snapshot in snapshots
        ],
        deltas=history_deltas(snapshots),
    )


@router.post("/stocks/{code}/feedback", response_model=FeedbackOut)
async def add_stock_feedback(
    code: str,
    payload: FeedbackIn,
    session: DB,
    user: CurrentUser,
) -> FeedbackOut:
    security = await stock_service.get_security(session, code)
    if security is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="security not found"
        )
    report = await session.get(Report, payload.report_id)
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="report not found"
        )
    await feedback_service.set_report_feedback(
        session,
        user.id,
        payload.report_id,
        security.id,
        action=payload.action,
    )
    return FeedbackOut(
        message="excluded",
        security_code=security.code,
        report_id=payload.report_id,
        excluded=True,
    )


@router.delete("/stocks/{code}/feedback/{report_id}", response_model=FeedbackOut)
async def remove_stock_feedback(
    code: str,
    report_id: int,
    session: DB,
    user: CurrentUser,
) -> FeedbackOut:
    security = await stock_service.get_security(session, code)
    if security is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="security not found"
        )
    removed = await feedback_service.remove_report_feedback(
        session, user.id, report_id, security.id
    )
    if not removed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="feedback not found"
        )
    return FeedbackOut(
        message="restored",
        security_code=security.code,
        report_id=report_id,
        excluded=False,
    )


__all__ = ["router"]
