from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.author import Author, AuthorIdentity
from app.models.channel import Channel
from app.models.report import Report, ReportAnalysis
from app.models.security import Security
from app.models.user import User


async def add_user(
    session: AsyncSession,
    *,
    email: str = "user@example.com",
    nickname: str = "测试用户",
    digest_email_enabled: bool = False,
    scoring_config: dict | None = None,
) -> User:
    user = User(
        email=email,
        password_hash="not-used-in-service-tests",
        nickname=nickname,
        digest_email_enabled=digest_email_enabled,
        scoring_config=scoring_config or {},
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def add_channel(
    session: AsyncSession,
    *,
    code: str,
    adapter_key: str = "mock",
    enabled: bool = True,
    config: dict | None = None,
    secret_ref: str | None = None,
) -> Channel:
    channel = Channel(
        code=code,
        name=code,
        adapter_key=adapter_key,
        enabled=enabled,
        config=config or {},
        secret_ref=secret_ref,
    )
    session.add(channel)
    await session.commit()
    await session.refresh(channel)
    return channel


async def add_author(
    session: AsyncSession,
    *,
    name: str,
    is_curated: bool = False,
    curated_rank: int = 0,
    crawl_enabled: bool = True,
    status: str = "active",
    default_weight: float = 1.0,
) -> Author:
    author = Author(
        canonical_name=name,
        normalized_name=name.strip().lower(),
        author_type="analyst",
        status=status,
        default_weight=default_weight,
        is_curated=is_curated,
        curated_rank=curated_rank,
        crawl_enabled=crawl_enabled,
    )
    session.add(author)
    await session.commit()
    await session.refresh(author)
    return author


async def add_identity(
    session: AsyncSession,
    author: Author,
    channel: Channel,
    external_id: str,
    *,
    display_name: str | None = None,
    profile_url: str | None = None,
) -> AuthorIdentity:
    identity = AuthorIdentity(
        author_id=author.id,
        channel_id=channel.id,
        external_id=external_id,
        display_name=display_name or author.canonical_name,
        profile_url=profile_url,
    )
    session.add(identity)
    await session.commit()
    await session.refresh(identity)
    return identity


async def add_security(
    session: AsyncSession,
    *,
    code: str,
    name: str,
    industry_code: str | None = None,
    symbol: str | None = None,
) -> Security:
    security = Security(
        code=code,
        symbol=symbol or code.split(".")[0],
        name=name,
        exchange="SH",
        industry_code=industry_code,
    )
    session.add(security)
    await session.commit()
    await session.refresh(security)
    return security


async def add_report(
    session: AsyncSession,
    channel: Channel,
    *,
    title: str,
    author: Author | None = None,
    published_at: datetime | None = None,
    score: float = 0.5,
    confidence: float = 0.8,
    primary_category: str = "stock",
    categories: list[str] | None = None,
    stock_codes: list[str] | None = None,
    industry_codes: list[str] | None = None,
    stock_mentions: list[dict[str, Any]] | None = None,
    industry_mentions: list[dict[str, Any]] | None = None,
    macro_mentions: list[dict[str, Any]] | None = None,
    analysis_status: str = "done",
) -> Report:
    published = published_at or datetime.now(UTC)
    report = Report(
        channel_id=channel.id,
        external_id=title,
        url=f"https://example.com/{abs(hash(title))}",
        title=title,
        content=title,
        author_id=author.id if author else None,
        raw_author_name=author.canonical_name if author else None,
        source_name="测试来源",
        published_at=published,
        content_hash=str(abs(hash(title))),
        primary_category=primary_category,
        categories=categories or [primary_category],
        stock_codes=stock_codes or [],
        industry_codes=industry_codes or [],
        score=score,
        confidence=confidence,
        analysis_status=analysis_status,
    )
    session.add(report)
    await session.flush()

    if analysis_status == "done":
        analysis = ReportAnalysis(
            report_id=report.id,
            model="test",
            primary_category=primary_category,
            categories=categories or [primary_category],
            score=score,
            confidence=confidence,
            direction="bullish" if score >= 0 else "bearish",
            summary=title,
            stock_mentions=stock_mentions or [],
            industry_mentions=industry_mentions or [],
            macro_mentions=macro_mentions or [],
        )
        session.add(analysis)
        await session.flush()
        report.current_analysis_id = analysis.id

    await session.commit()
    await session.refresh(report)
    return report
