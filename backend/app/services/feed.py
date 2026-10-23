from __future__ import annotations

import base64
import binascii
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import DEFAULT_CATEGORY_WEIGHTS, display_score
from app.models.author import Author
from app.models.personalization import AuthorFollow, ReportInteraction
from app.models.report import Report, ReportAnalysis
from app.scoring.feed import DiversityLimits, diversify, hot_score, smart_score

WINDOW_DELTAS = {
    "24h": timedelta(hours=24),
    "72h": timedelta(hours=72),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
}

DEFAULT_WINDOWS = {"following": "7d", "discover": "72h"}


@dataclass
class FeedOptions:
    scope: str = "following"
    sort: str = "smart"
    window: str | None = None
    limit: int = 20
    cursor: str | None = None
    category: str | None = None
    stock_code: str | None = None


@dataclass
class FeedRow:
    report: Report
    author: Author | None
    follow: AuthorFollow | None
    sort_score: float = 0.0


def encode_cursor(offset: int) -> str:
    return base64.urlsafe_b64encode(json.dumps({"o": offset}).encode()).decode()


def decode_cursor(cursor: str | None) -> int:
    if not cursor:
        return 0
    try:
        payload = json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())
        return max(0, int(payload.get("o", 0)))
    except (ValueError, binascii.Error, json.JSONDecodeError):
        return 0


def _engagement_total(engagement: dict | None) -> int:
    if not engagement:
        return 0
    total = 0
    for value in engagement.values():
        if isinstance(value, (int, float)):
            total += int(value)
    return total


async def get_feed(session: AsyncSession, user_id: int, options: FeedOptions) -> dict:
    now = datetime.now(UTC)
    window = options.window or DEFAULT_WINDOWS.get(options.scope, "7d")
    offset = decode_cursor(options.cursor)
    limit = max(1, min(options.limit, 50))

    followed_ids = set(
        (
            await session.scalars(
                select(AuthorFollow.author_id).where(AuthorFollow.user_id == user_id)
            )
        ).all()
    )

    if options.scope == "following" and not followed_ids:
        return {
            "items": [],
            "next_cursor": None,
            "has_more": False,
            "scope": options.scope,
            "sort": options.sort,
            "generated_at": now,
        }

    hidden_reports = select(ReportInteraction.report_id).where(
        ReportInteraction.user_id == user_id,
        ReportInteraction.hidden.is_(True),
    )

    stmt = (
        select(Report, Author, AuthorFollow)
        .outerjoin(Author, Report.author_id == Author.id)
        .outerjoin(
            AuthorFollow,
            and_(
                AuthorFollow.author_id == Report.author_id,
                AuthorFollow.user_id == user_id,
            ),
        )
        .where(Report.analysis_status == "done")
        .where(~Report.id.in_(hidden_reports))
    )

    if options.scope == "following":
        stmt = stmt.where(Report.author_id.in_(followed_ids))

    if window != "all":
        delta = WINDOW_DELTAS.get(window, WINDOW_DELTAS["7d"])
        stmt = stmt.where(Report.published_at >= now - delta)

    pool_size = min(400, (offset + limit) * 4 + 20)
    stmt = stmt.order_by(Report.published_at.desc()).limit(pool_size)
    rows = (await session.execute(stmt)).all()

    feed_rows: list[FeedRow] = []
    for report, author, follow in rows:
        if options.category and options.category not in (report.categories or []):
            if report.primary_category != options.category:
                continue
        if options.stock_code:
            code = options.stock_code.upper()
            if code not in (report.stock_codes or []):
                continue
        feed_rows.append(FeedRow(report=report, author=author, follow=follow))

    for row in feed_rows:
        default_weight = row.author.default_weight if row.author else 0.5
        personal_weight = row.follow.weight if row.follow else default_weight
        if options.sort == "hot":
            row.sort_score = hot_score(
                default_weight=default_weight,
                published_at=row.report.published_at,
                confidence=row.report.confidence,
                score=row.report.score,
                reprint_count=row.report.reprint_count,
                engagement=_engagement_total(row.report.engagement),
                now=now,
            )
        elif options.sort == "smart":
            row.sort_score = smart_score(
                published_at=row.report.published_at,
                confidence=row.report.confidence,
                score=row.report.score,
                category_weight=DEFAULT_CATEGORY_WEIGHTS.get(
                    row.report.primary_category or "industry", 0.25
                ),
                author_weight=personal_weight,
                priority=row.follow is not None,
                now=now,
            )
        else:
            row.sort_score = row.report.published_at.timestamp()

    if options.sort in {"hot", "smart"}:
        feed_rows.sort(key=lambda row: row.sort_score, reverse=True)

    deduped: list[FeedRow] = []
    seen_clusters: set[int] = set()
    for row in feed_rows:
        cluster = row.report.cluster_id
        if cluster is not None and cluster in seen_clusters:
            continue
        if cluster is not None:
            seen_clusters.add(cluster)
        deduped.append(row)

    limit_config = DiversityLimits(max_per_author=2, max_per_category=6, window=20)
    diversified = diversify(
        deduped,
        key_author=lambda row: row.report.author_id,
        key_cluster=lambda row: row.report.cluster_id,
        key_category=lambda row: row.report.primary_category,
        limit=offset + limit,
        limits=limit_config,
    )
    page = diversified[offset : offset + limit]
    has_more = len(diversified) > offset + limit

    return {
        "items": [serialize_report(row.report, row.author, row.follow, now=now) for row in page],
        "next_cursor": encode_cursor(offset + limit) if has_more else None,
        "has_more": has_more,
        "scope": options.scope,
        "sort": options.sort,
        "generated_at": now,
    }


def serialize_report(
    report: Report,
    author: Author | None,
    follow: AuthorFollow | None,
    *,
    now: datetime | None = None,
) -> dict:
    return {
        "id": report.id,
        "channel_id": report.channel_id,
        "url": report.url,
        "title": report.title,
        "summary": report.summary,
        "opinion": report.opinion,
        "published_at": report.published_at,
        "source_name": report.source_name,
        "author": {
            "id": author.id if author else None,
            "name": author.canonical_name if author else (report.raw_author_name or "未知"),
            "weight": follow.weight if follow else (author.default_weight if author else 0.5),
            "followed": follow is not None,
            "is_curated": bool(author.is_curated) if author else False,
            "source_layer": (
                "following"
                if follow is not None
                else "curated"
                if author is not None and author.is_curated
                else "market"
            ),
        },
        "primary_category": report.primary_category,
        "categories": report.categories or [],
        "stock_codes": report.stock_codes or [],
        "industry_codes": report.industry_codes or [],
        "macro_tags": report.macro_tags or [],
        "keywords": report.keywords or [],
        "score": report.score,
        "display_score": display_score(report.score),
        "confidence": report.confidence,
        "direction": report.direction,
        "horizon": report.horizon,
        "cluster_id": report.cluster_id,
        "reprint_count": report.reprint_count,
        "is_reprint": report.is_reprint,
    }


async def get_report_detail(
    session: AsyncSession,
    report_id: int,
    user_id: int,
) -> dict | None:
    row = (
        await session.execute(
            select(Report, Author, AuthorFollow, ReportInteraction)
            .outerjoin(Author, Report.author_id == Author.id)
            .outerjoin(
                AuthorFollow,
                and_(
                    AuthorFollow.author_id == Report.author_id,
                    AuthorFollow.user_id == user_id,
                ),
            )
            .outerjoin(
                ReportInteraction,
                and_(
                    ReportInteraction.report_id == Report.id,
                    ReportInteraction.user_id == user_id,
                ),
            )
            .where(Report.id == report_id)
        )
    ).first()
    if row is None:
        return None

    report, author, follow, _interaction = row
    data = serialize_report(report, author, follow)
    data["content"] = report.content

    analysis: ReportAnalysis | None = None
    if report.current_analysis_id:
        analysis = await session.get(ReportAnalysis, report.current_analysis_id)
    if analysis is None:
        analysis = await session.scalar(
            select(ReportAnalysis)
            .where(ReportAnalysis.report_id == report.id)
            .order_by(ReportAnalysis.created_at.desc())
            .limit(1)
        )

    data.update(
        {
            "key_points": analysis.key_points if analysis else [],
            "rationale": analysis.rationale if analysis else None,
            "stock_mentions": analysis.stock_mentions if analysis else [],
            "industry_mentions": analysis.industry_mentions if analysis else [],
            "macro_mentions": analysis.macro_mentions if analysis else [],
            "analysis_model": analysis.model if analysis else None,
            "analyzed_at": analysis.created_at if analysis else None,
        }
    )
    return data


async def set_interaction(
    session: AsyncSession,
    user_id: int,
    report_id: int,
    *,
    saved: bool | None = None,
    hidden: bool | None = None,
    read: bool | None = None,
) -> ReportInteraction:
    interaction = await session.scalar(
        select(ReportInteraction).where(
            ReportInteraction.user_id == user_id,
            ReportInteraction.report_id == report_id,
        )
    )
    if interaction is None:
        interaction = ReportInteraction(user_id=user_id, report_id=report_id)
        session.add(interaction)
    if saved is not None:
        interaction.saved = saved
    if hidden is not None:
        interaction.hidden = hidden
    if read:
        interaction.read_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(interaction)
    return interaction
