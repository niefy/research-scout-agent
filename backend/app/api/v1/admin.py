from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select

from app.api.deps import DB, AdminUser
from app.collectors.registry import list_adapters
from app.models.author import Author
from app.models.channel import Channel
from app.models.job import IngestRun, LLMCallLog
from app.models.report import Report
from app.models.user import User
from app.schemas.admin import (
    AdapterOut,
    AnalyzeRequest,
    AnalyzeResponse,
    ChannelOut,
    ChannelUpdate,
    CrawlChannelResult,
    CrawlRequest,
    CrawlResponse,
    IngestRunOut,
    SystemStatsOut,
)
from app.services.analysis import analyze_pending, today_start
from app.services.ingest import crawl_channels

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[])


@router.get("/channels", response_model=list[ChannelOut])
async def list_channels(session: DB, admin: AdminUser) -> list[ChannelOut]:
    rows = (await session.scalars(select(Channel).order_by(Channel.id))).all()
    return [ChannelOut.model_validate(row) for row in rows]


@router.patch("/channels/{code}", response_model=ChannelOut)
async def update_channel(
    code: str,
    payload: ChannelUpdate,
    session: DB,
    admin: AdminUser,
) -> ChannelOut:
    channel = await session.scalar(select(Channel).where(Channel.code == code))
    if channel is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="channel not found")
    if payload.enabled is not None:
        channel.enabled = payload.enabled
    if payload.config is not None:
        channel.config = payload.config
    if payload.crawl_interval_seconds is not None:
        channel.crawl_interval_seconds = payload.crawl_interval_seconds
    await session.commit()
    await session.refresh(channel)
    return ChannelOut.model_validate(channel)


@router.get("/adapters", response_model=list[AdapterOut])
async def list_channel_adapters(admin: AdminUser) -> list[AdapterOut]:
    return [
        AdapterOut(key=adapter.key, display_name=adapter.display_name)
        for adapter in list_adapters()
    ]


@router.post("/crawl", response_model=CrawlResponse)
async def trigger_crawl(
    payload: CrawlRequest,
    session: DB,
    admin: AdminUser,
) -> CrawlResponse:
    results = await crawl_channels(
        session,
        channel_codes=payload.channel_codes,
        limit=payload.limit,
    )
    analyzed = 0
    failed = 0
    if payload.analyze:
        stats = await analyze_pending(session, limit=200)
        analyzed = stats["analyzed"]
        failed = stats["failed"]
    return CrawlResponse(
        results=[CrawlChannelResult(**result) for result in results],
        analyzed=analyzed,
        analysis_failed=failed,
    )


@router.post("/analyze", response_model=AnalyzeResponse)
async def trigger_analysis(
    payload: AnalyzeRequest,
    session: DB,
    admin: AdminUser,
) -> AnalyzeResponse:
    stats = await analyze_pending(
        session,
        limit=payload.limit,
        report_ids=payload.report_ids,
        force=payload.force,
    )
    return AnalyzeResponse(**stats)


@router.get("/jobs", response_model=list[IngestRunOut])
async def list_jobs(
    session: DB,
    admin: AdminUser,
    limit: int = Query(default=20, ge=1, le=100),
) -> list[IngestRunOut]:
    rows = (
        await session.scalars(select(IngestRun).order_by(IngestRun.id.desc()).limit(limit))
    ).all()
    return [IngestRunOut.model_validate(row) for row in rows]


@router.get("/stats", response_model=SystemStatsOut)
async def system_stats(session: DB, admin: AdminUser) -> SystemStatsOut:
    start = today_start()
    reports_total = await session.scalar(select(func.count(Report.id))) or 0
    reports_analyzed = (
        await session.scalar(
            select(func.count(Report.id)).where(Report.analysis_status == "done")
        )
        or 0
    )
    authors_total = await session.scalar(select(func.count(Author.id))) or 0
    users_total = await session.scalar(select(func.count(User.id))) or 0
    channels_enabled = (
        await session.scalar(
            select(func.count(Channel.id)).where(Channel.enabled.is_(True))
        )
        or 0
    )
    llm_calls, llm_tokens = (
        await session.execute(
            select(
                func.count(LLMCallLog.id),
                func.coalesce(func.sum(LLMCallLog.input_tokens + LLMCallLog.output_tokens), 0),
            ).where(LLMCallLog.created_at >= start)
        )
    ).one()
    llm_fallbacks = (
        await session.scalar(
            select(func.count(LLMCallLog.id)).where(
                LLMCallLog.created_at >= start,
                LLMCallLog.fallback.is_(True),
            )
        )
        or 0
    )
    return SystemStatsOut(
        reports_total=reports_total,
        reports_analyzed=reports_analyzed,
        authors_total=authors_total,
        users_total=users_total,
        channels_enabled=channels_enabled,
        llm_calls_today=int(llm_calls or 0),
        llm_tokens_today=int(llm_tokens or 0),
        llm_fallbacks_today=int(llm_fallbacks),
    )
