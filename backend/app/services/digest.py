from __future__ import annotations

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.author import Author
from app.models.personalization import AuthorFollow, ReportInteraction, WatchlistItem
from app.models.report import Report
from app.models.security import Security
from app.models.user import User
from app.services.feed import serialize_report
from app.services.snapshots import local_day_bounds_utc, local_day_start_utc
from app.services.stocks import (
    compute_stock_score,
    load_report_pool,
    normalize_scope,
)

FOLLOWED_LIMIT = 10
RECOMMENDED_LIMIT = 5
WATCHLIST_LIMIT = 20


def _security_payload(security: Security) -> dict:
    return {
        "id": security.id,
        "code": security.code,
        "symbol": security.symbol,
        "name": security.name,
        "exchange": security.exchange,
        "industry_code": security.industry_code,
        "aliases": security.aliases or [],
    }


def _evidence_gaps(score) -> list[str]:
    gaps: list[str] = []
    evidence = score.evidence
    if score.report_count == 0:
        gaps.append("no_reports")
    if evidence.stock_count == 0:
        gaps.append("missing_stock")
    if evidence.industry_count == 0:
        gaps.append("missing_industry")
    if evidence.is_macro_only:
        gaps.append("macro_only")
    return gaps


async def build_digest(
    session: AsyncSession,
    user: User,
    *,
    scope: str | None = None,
    window: str = "30d",
    digest_date: date | None = None,
) -> dict:
    from app.services.feedback import load_excluded_report_ids_by_security
    from app.services.snapshots import load_previous_snapshots

    if digest_date is None:
        digest_date = datetime.now(ZoneInfo(settings.timezone)).date()

    resolved_scope = normalize_scope(scope, user)
    start, end = local_day_bounds_utc(digest_date)
    now = datetime.now(UTC)

    followed_ids = set(
        (
            await session.scalars(
                select(AuthorFollow.author_id).where(AuthorFollow.user_id == user.id)
            )
        ).all()
    )

    followed_updates: list[dict] = []
    if followed_ids:
        hidden = select(ReportInteraction.report_id).where(
            ReportInteraction.user_id == user.id,
            ReportInteraction.hidden.is_(True),
        )
        rows = (
            await session.execute(
                select(Report, Author, AuthorFollow)
                .outerjoin(Author, Report.author_id == Author.id)
                .outerjoin(
                    AuthorFollow,
                    and_(
                        AuthorFollow.author_id == Report.author_id,
                        AuthorFollow.user_id == user.id,
                    ),
                )
                .where(
                    Report.author_id.in_(followed_ids),
                    Report.analysis_status == "done",
                    Report.published_at >= start,
                    Report.published_at <= end,
                    ~Report.id.in_(hidden),
                )
                .order_by(Report.published_at.desc())
                .limit(FOLLOWED_LIMIT)
            )
        ).all()
        followed_updates = [
            serialize_report(report, author, follow, now=now)
            for report, author, follow in rows
        ]

    rows = (
        await session.execute(
            select(WatchlistItem, Security)
            .join(Security, WatchlistItem.security_id == Security.id)
            .where(WatchlistItem.user_id == user.id)
            .order_by(WatchlistItem.sort_order, WatchlistItem.id)
            .limit(WATCHLIST_LIMIT)
        )
    ).all()

    watchlist_changes: list[dict] = []
    evidence_gaps: list[dict] = []
    if rows:
        security_ids = [security.id for _, security in rows]
        pool = await load_report_pool(
            session, user.id, scope=resolved_scope, window=window
        )
        exclusions = await load_excluded_report_ids_by_security(session, user.id)
        previous = await load_previous_snapshots(
            session,
            user.id,
            security_ids,
            scope=resolved_scope,
            window=window,
            before=local_day_start_utc(digest_date),
        )
        for _item, security in rows:
            score = await compute_stock_score(
                session,
                user.id,
                security,
                scope=resolved_scope,
                window=window,
                pool=pool,
                excluded_report_ids=exclusions.get(security.id, set()),
            )
            prior = previous.get(security.id)
            if prior is not None:
                score.previous_total_points = prior.total_points
                score.delta_since = prior.computed_at
            gaps = _evidence_gaps(score)
            change = {
                "security": _security_payload(security),
                "display_score": score.display_score,
                "display_label": score.display_label,
                "evidence": score.evidence.as_dict(),
                "relation_counts": score.result.relation_counts,
                "report_count": score.report_count,
                "previous_total_points": score.previous_total_points,
                "score_delta": score.delta_points,
                "delta_since": score.delta_since,
                "evidence_gaps": gaps,
            }
            watchlist_changes.append(change)
            if gaps:
                evidence_gaps.append(
                    {
                        "security": _security_payload(security),
                        "gaps": gaps,
                        "evidence_level": score.evidence.level,
                    }
                )

    watchlist_changes.sort(
        key=lambda item: (
            abs(item["score_delta"]) if item["score_delta"] is not None else -1,
            item["display_score"] or 0,
        ),
        reverse=True,
    )

    recommended_stmt = select(Author).where(
        Author.is_curated.is_(True),
        Author.status == "active",
    )
    if followed_ids:
        recommended_stmt = recommended_stmt.where(Author.id.not_in(followed_ids))
    recommended_rows = (
        await session.scalars(
            recommended_stmt
            .order_by(Author.curated_rank.desc(), Author.id)
            .limit(RECOMMENDED_LIMIT)
        )
    ).all()
    recommended_authors = [
        {
            "id": author.id,
            "canonical_name": author.canonical_name,
            "author_type": author.author_type,
            "quality_score": author.quality_score,
            "sector_tags": author.sector_tags or [],
            "curated_rank": author.curated_rank,
            "last_crawled_at": author.last_crawled_at,
        }
        for author in recommended_rows
    ]

    return {
        "date": digest_date.isoformat(),
        "generated_at": now,
        "user": {"id": user.id, "nickname": user.nickname, "email": user.email},
        "scope": resolved_scope,
        "window": window,
        "followed_updates": followed_updates,
        "watchlist_changes": watchlist_changes,
        "evidence_gaps": evidence_gaps,
        "recommended_authors": recommended_authors,
        "has_content": bool(
            followed_updates or watchlist_changes or recommended_authors
        ),
    }


__all__ = ["build_digest"]
