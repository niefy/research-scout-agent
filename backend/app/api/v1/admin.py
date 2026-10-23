from __future__ import annotations

import os
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, or_, select

from app.api.deps import DB, AdminUser
from app.collectors.registry import list_adapters
from app.core.config import settings
from app.models.author import Author, AuthorIdentity
from app.models.channel import Channel
from app.models.job import IngestRun, LLMCallLog
from app.models.personalization import AuthorFollow
from app.models.report import Report
from app.models.user import User
from app.schemas.admin import (
    AdapterOut,
    AnalyzeRequest,
    AnalyzeResponse,
    AuthorCrawlRequest,
    AuthorCrawlResponse,
    AuthorCurationUpdate,
    AuthorIdentityBindOut,
    AuthorIdentityIn,
    ChannelOut,
    ChannelUpdate,
    CrawlChannelResult,
    CrawlRequest,
    CrawlResponse,
    IngestRunOut,
    SourceHealthAuthorOut,
    SourceHealthChannelOut,
    SourceHealthOut,
    SystemStatsOut,
)
from app.schemas.author import AuthorOut
from app.schemas.digest import DigestSendIn, DigestSendOut
from app.services.analysis import analyze_pending, today_start
from app.services.author_crawl import analyze_author_reports, crawl_author_targets
from app.services.digest_email import send_daily_digests
from app.services.email import EmailNotConfigured
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


@router.patch("/authors/{author_id}/curation", response_model=AuthorOut)
async def update_author_curation(
    author_id: int,
    payload: AuthorCurationUpdate,
    session: DB,
    admin: AdminUser,
) -> AuthorOut:
    author = await session.get(Author, author_id)
    if author is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="author not found"
        )
    if payload.is_curated is not None:
        author.is_curated = payload.is_curated
    if payload.curated_rank is not None:
        author.curated_rank = payload.curated_rank
    if payload.crawl_enabled is not None:
        author.crawl_enabled = payload.crawl_enabled
    if payload.quality_score is not None:
        author.quality_score = payload.quality_score
    if payload.sector_tags is not None:
        author.sector_tags = list(payload.sector_tags)
    await session.commit()
    await session.refresh(author)
    return AuthorOut.model_validate(author)


@router.put(
    "/authors/{author_id}/identities", response_model=AuthorIdentityBindOut
)
async def bind_author_identity(
    author_id: int,
    payload: AuthorIdentityIn,
    session: DB,
    admin: AdminUser,
) -> AuthorIdentityBindOut:
    author = await session.get(Author, author_id)
    if author is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="author not found"
        )
    channel = await session.scalar(
        select(Channel).where(Channel.code == payload.channel_code)
    )
    if channel is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="channel not found"
        )
    identity = await session.scalar(
        select(AuthorIdentity).where(
            AuthorIdentity.channel_id == channel.id,
            AuthorIdentity.external_id == payload.external_id,
        )
    )
    if identity is not None and identity.author_id != author_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="identity is already bound to another author",
        )
    if identity is None:
        identity = AuthorIdentity(
            author_id=author_id,
            channel_id=channel.id,
            external_id=payload.external_id,
        )
        session.add(identity)
    identity.display_name = payload.display_name or author.canonical_name
    identity.profile_url = (
        payload.profile_url
        or f"https://xueqiu.com/u/{payload.external_id}"
    )
    await session.commit()
    await session.refresh(identity)
    return AuthorIdentityBindOut(
        author_id=author_id,
        channel_id=identity.channel_id,
        external_id=identity.external_id,
        display_name=identity.display_name,
        profile_url=identity.profile_url,
    )


@router.post("/author-crawl", response_model=AuthorCrawlResponse)
async def trigger_author_crawl(
    payload: AuthorCrawlRequest,
    session: DB,
    admin: AdminUser,
) -> AuthorCrawlResponse:
    result = await crawl_author_targets(
        session,
        author_ids=payload.author_ids,
        limit=payload.limit,
        force=payload.force,
    )
    if payload.analyze:
        result["analysis"] = await analyze_author_reports(
            session, result.get("created_report_ids", [])
        )
    return AuthorCrawlResponse(**result)


@router.get("/source-health", response_model=SourceHealthOut)
async def source_health(session: DB, admin: AdminUser) -> SourceHealthOut:
    channels = list((await session.scalars(select(Channel).order_by(Channel.id))).all())
    channel_health: list[SourceHealthChannelOut] = []
    for channel in channels:
        latest = await session.scalar(
            select(IngestRun)
            .where(IngestRun.channel_id == channel.id)
            .order_by(IngestRun.id.desc())
            .limit(1)
        )
        credential_configured: bool | None = None
        if channel.secret_ref:
            credential_configured = bool(
                settings.xueqiu_cookie.strip()
                or (os.environ.get(channel.secret_ref) or "").strip()
            )
        stats = (latest.stats if latest else {}) or {}
        channel_health.append(
            SourceHealthChannelOut(
                channel_code=channel.code,
                name=channel.name,
                adapter_key=channel.adapter_key,
                enabled=channel.enabled,
                credential_configured=credential_configured,
                last_run_at=latest.finished_at if latest else None,
                last_status=latest.status if latest else None,
                last_error=latest.error if latest else None,
                last_fetched=int(stats.get("fetched") or 0),
                last_created=int(stats.get("created") or 0),
            )
        )

    authors = list(
        (
            await session.scalars(
                select(Author)
                .where(
                    Author.status == "active",
                    or_(
                        Author.is_curated.is_(True),
                        Author.id.in_(select(AuthorFollow.author_id)),
                    ),
                )
                .order_by(Author.curated_rank.desc(), Author.id)
                .limit(100)
            )
        ).all()
    )
    identity_counts: dict[int, int] = {}
    if authors:
        counts = (
            await session.execute(
                select(AuthorIdentity.author_id, func.count(AuthorIdentity.id))
                .where(AuthorIdentity.author_id.in_([author.id for author in authors]))
                .group_by(AuthorIdentity.author_id)
            )
        ).all()
        identity_counts = {author_id: count for author_id, count in counts}

    return SourceHealthOut(
        generated_at=datetime.now(UTC),
        channels=channel_health,
        authors=[
            SourceHealthAuthorOut(
                author_id=author.id,
                canonical_name=author.canonical_name,
                is_curated=author.is_curated,
                crawl_enabled=author.crawl_enabled,
                crawl_status=author.crawl_status,
                last_crawled_at=author.last_crawled_at,
                crawl_error=author.crawl_error,
                identity_count=identity_counts.get(author.id, 0),
            )
            for author in authors
        ],
    )


@router.post("/digest/send", response_model=DigestSendOut)
async def trigger_digest_send(
    payload: DigestSendIn,
    session: DB,
    admin: AdminUser,
) -> DigestSendOut:
    try:
        stats = await send_daily_digests(
            session,
            digest_date=payload.date,
            user_id=payload.user_id,
        )
    except EmailNotConfigured as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    return DigestSendOut(**stats)


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
