from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import (
    CATEGORY_BUDGET_WEIGHTS,
    DEFAULT_HALF_LIFE_DAYS,
    MAX_REPORT_AGE_DAYS,
)
from app.models.author import Author
from app.models.personalization import AuthorFollow, WatchlistItem
from app.models.report import Report, ReportAnalysis
from app.models.security import Security
from app.models.user import User
from app.scoring.stock import AggregateResult, ScoreInput, aggregate_scores
from app.services.feed import serialize_report

# Stock aggregation never looks further back than three months.
WINDOW_DELTAS = {
    "7d": 7,
    "30d": 30,
    "90d": int(MAX_REPORT_AGE_DAYS),
    "all": int(MAX_REPORT_AGE_DAYS),
}
POOL_LIMIT = 1200

WINDOW_LABELS = {"7d": "7天", "30d": "30天", "90d": "3个月", "all": "3个月"}


class StockNotFoundError(LookupError):
    pass


class WatchlistDuplicateError(ValueError):
    pass


@dataclass
class PoolEntry:
    report: Report
    author: Author | None
    follow: AuthorFollow | None
    analysis: ReportAnalysis | None


@dataclass
class StockScore:
    security: Security
    scope: str
    window: str
    result: AggregateResult
    entries: list[PoolEntry]
    conclusion: str
    display_score: float | None
    category_weights: dict[str, float]
    half_life_days: dict[str, float]

    @property
    def report_count(self) -> int:
        return self.result.report_count


def _scoring_config(user: User | None) -> tuple[dict[str, float], dict[str, float]]:
    config = (user.scoring_config if user else {}) or {}
    raw_weights = config.get("category_weights") or {}
    raw_half_lives = config.get("half_life_days") or {}

    weights = dict(CATEGORY_BUDGET_WEIGHTS)
    for key, value in raw_weights.items():
        if key in weights and isinstance(value, (int, float)) and value >= 0:
            weights[key] = float(value)

    half_lives = dict(DEFAULT_HALF_LIFE_DAYS)
    for key, value in raw_half_lives.items():
        if key in half_lives and isinstance(value, (int, float)) and value > 0:
            half_lives[key] = float(value)
    return weights, half_lives


def _window_cutoff(window: str) -> datetime:
    days = min(WINDOW_DELTAS.get(window, WINDOW_DELTAS["30d"]), int(MAX_REPORT_AGE_DAYS))
    return datetime.now(UTC) - timedelta(days=days)


async def load_report_pool(
    session: AsyncSession,
    user_id: int,
    *,
    scope: str = "all",
    window: str = "30d",
) -> list[PoolEntry]:
    cutoff = _window_cutoff(window)
    stmt = (
        select(Report, Author, AuthorFollow, ReportAnalysis)
        .outerjoin(Author, Report.author_id == Author.id)
        .outerjoin(
            AuthorFollow,
            and_(
                AuthorFollow.author_id == Report.author_id,
                AuthorFollow.user_id == user_id,
            ),
        )
        .outerjoin(ReportAnalysis, Report.current_analysis_id == ReportAnalysis.id)
        .where(Report.analysis_status == "done")
    )
    if scope == "followed":
        followed_ids = select(AuthorFollow.author_id).where(AuthorFollow.user_id == user_id)
        stmt = stmt.where(Report.author_id.in_(followed_ids))
    if cutoff is not None:
        stmt = stmt.where(Report.published_at >= cutoff)
    stmt = stmt.order_by(Report.published_at.desc()).limit(POOL_LIMIT)

    rows = (await session.execute(stmt)).all()
    return [
        PoolEntry(report=report, author=author, follow=follow, analysis=analysis)
        for report, author, follow, analysis in rows
    ]


def _match_report(entry: PoolEntry, security: Security) -> tuple[float, float] | None:
    """Return (relevance, score) if the report is relevant to the security."""
    report = entry.report
    code = security.code.upper()

    mentions = entry.analysis.stock_mentions if entry.analysis else []
    for mention in mentions:
        mention_code = str(mention.get("code") or "").upper()
        if mention_code == code:
            sentiment = float(mention.get("sentiment") or 0.0)
            score = sentiment if abs(sentiment) >= 0.05 else float(report.score or 0.0)
            relevance = max(0.5, min(1.0, float(mention.get("relevance") or 0.8)))
            return relevance, score

    if code in {str(item).upper() for item in (report.stock_codes or [])}:
        return 0.7, float(report.score or 0.0)

    categories = report.categories or []
    if (
        security.industry_code
        and security.industry_code in (report.industry_codes or [])
        and (report.primary_category == "industry" or "industry" in categories)
    ):
        return 0.75, float(report.score or 0.0)

    if report.primary_category == "macro":
        return 0.45, float(report.score or 0.0)

    return None


def _build_conclusion(
    security: Security,
    result: AggregateResult,
    window: str,
) -> str:
    if result.report_count == 0:
        return f"{security.name}暂无足够的相关分析，建议关注更多相关作者或等待新报告。"

    if result.final_score >= 0.15:
        stance = "综合信号偏多"
    elif result.final_score <= -0.15:
        stance = "综合信号偏空"
    else:
        stance = "综合信号中性"

    counts = result.category_counts
    labels = {"stock": "个股", "industry": "行业", "macro": "宏观"}
    count_text = "、".join(
        f"{labels[key]}{counts.get(key, 0)}条"
        for key in ("stock", "industry", "macro")
        if counts.get(key, 0)
    )
    breakdown_text = "、".join(
        f"{labels[item.category]}{item.points:.0f}/{item.budget_points:.0f}"
        for item in result.category_scores
    )
    confidence_text = "证据较集中" if result.n_eff < 3 else "信源相对分散"
    top = sorted(
        result.breakdown,
        key=lambda item: item.effective_weight * abs(item.score),
        reverse=True,
    )[:2]
    top_text = ""
    if top:
        top_text = "；主要驱动：" + "、".join(f"《{item.title[:28]}》" for item in top)

    window_label = WINDOW_LABELS.get(window, window)
    score_text = f"综合得分{result.total_points:.0f}/100"
    tail = f"{confidence_text}{top_text}"
    return (
        f"{security.name}近{window_label}纳入{result.report_count}条相关报告（{count_text}），"
        f"{stance}，{score_text}。板块构成：{breakdown_text}；{tail}"
    )


def _score_entries(
    security: Security,
    pool: list[PoolEntry],
    *,
    user: User | None,
    scope: str,
    window: str,
) -> StockScore:
    category_weights, half_lives = _scoring_config(user)
    matched: list[tuple[PoolEntry, float, float]] = []
    for entry in pool:
        match = _match_report(entry, security)
        if match is None:
            continue
        relevance, score = match
        matched.append((entry, relevance, score))

    score_inputs = [
        ScoreInput(
            report_id=entry.report.id,
            title=entry.report.title,
            category=entry.report.primary_category or "macro",
            score=score,
            confidence=float(entry.report.confidence or 0.0),
            author_weight=(
                entry.follow.weight
                if entry.follow
                else (entry.author.default_weight if entry.author else 0.5)
            ),
            published_at=entry.report.published_at,
            relevance=relevance,
        )
        for entry, relevance, score in matched
    ]
    result = aggregate_scores(
        score_inputs,
        category_weights=category_weights,
        half_life_days=half_lives,
        max_age_days=MAX_REPORT_AGE_DAYS,
    )
    conclusion = _build_conclusion(security, result, window)
    included_ids = {item.report_id for item in result.breakdown}
    return StockScore(
        security=security,
        scope=scope,
        window=window,
        result=result,
        entries=[entry for entry, _, _ in matched if entry.report.id in included_ids],
        conclusion=conclusion,
        display_score=result.total_points if result.report_count else None,
        category_weights=category_weights,
        half_life_days=half_lives,
    )


async def compute_stock_score(
    session: AsyncSession,
    user_id: int,
    security: Security,
    *,
    scope: str = "all",
    window: str = "30d",
    pool: list[PoolEntry] | None = None,
) -> StockScore:
    user = await session.get(User, user_id)
    pool = (
        pool
        if pool is not None
        else await load_report_pool(session, user_id, scope=scope, window=window)
    )
    return _score_entries(
        security,
        pool,
        user=user,
        scope=scope,
        window=window,
    )


def serialize_stock_score(score: StockScore) -> dict:
    result = score.result
    return {
        "security": {
            "id": score.security.id,
            "code": score.security.code,
            "symbol": score.security.symbol,
            "name": score.security.name,
            "exchange": score.security.exchange,
            "industry_code": score.security.industry_code,
            "aliases": score.security.aliases or [],
        },
        "scope": score.scope,
        "window": score.window,
        "report_count": result.report_count,
        "raw_score": result.raw_score,
        "final_score": result.final_score,
        "total_points": result.total_points,
        "display_score": score.display_score,
        "n_eff": result.n_eff,
        "confidence": result.confidence,
        "conclusion": score.conclusion,
        "category_scores": [
            {
                "category": item.category,
                "budget_share": item.budget_share,
                "budget_points": item.budget_points,
                "article_count": item.article_count,
                "weighted_signal": item.weighted_signal,
                "points": item.points,
                "weight_sum": item.weight_sum,
                "confidence": item.confidence,
            }
            for item in result.category_scores
        ],
        "category_weights": score.category_weights,
        "half_life_days": score.half_life_days,
        "max_age_days": MAX_REPORT_AGE_DAYS,
        "breakdown": [
            {
                "report_id": item.report_id,
                "title": item.title,
                "category": item.category,
                "score": item.score,
                "confidence": item.confidence,
                "author_weight": item.author_weight,
                "category_weight": item.category_weight,
                "recency_factor": item.recency_factor,
                "relevance": item.relevance,
                "effective_weight": item.effective_weight,
                "published_at": item.published_at,
            }
            for item in result.breakdown
        ],
        "category_counts": result.category_counts,
        "computed_at": datetime.now(UTC),
    }


async def get_security(session: AsyncSession, code: str) -> Security | None:
    value = code.strip()
    return await session.scalar(
        select(Security).where(
            or_(
                Security.code == value.upper(),
                Security.symbol == value,
                Security.name == value,
            )
        )
    )


async def search_securities(
    session: AsyncSession,
    query: str,
    *,
    limit: int = 20,
) -> list[Security]:
    pattern = f"%{query.strip()}%"
    return list(
        (
            await session.scalars(
                select(Security)
                .where(
                    Security.enabled.is_(True),
                    or_(
                        Security.code.ilike(pattern),
                        Security.symbol.ilike(pattern),
                        Security.name.ilike(pattern),
                    ),
                )
                .order_by(Security.code)
                .limit(limit)
            )
        ).all()
    )


async def list_watchlist(
    session: AsyncSession,
    user_id: int,
    *,
    scope: str = "all",
    window: str = "30d",
) -> list[dict]:
    rows = (
        await session.execute(
            select(WatchlistItem, Security)
            .join(Security, WatchlistItem.security_id == Security.id)
            .where(WatchlistItem.user_id == user_id)
            .order_by(WatchlistItem.sort_order, WatchlistItem.id)
        )
    ).all()
    if not rows:
        return []

    pool = await load_report_pool(session, user_id, scope=scope, window=window)
    items = []
    for item, security in rows:
        score = await compute_stock_score(
            session,
            user_id,
            security,
            scope=scope,
            window=window,
            pool=pool,
        )
        items.append(
            {
                "id": item.id,
                "security": {
                    "id": security.id,
                    "code": security.code,
                    "symbol": security.symbol,
                    "name": security.name,
                    "exchange": security.exchange,
                    "industry_code": security.industry_code,
                    "aliases": security.aliases or [],
                },
                "note": item.note,
                "sort_order": item.sort_order,
                "score": serialize_stock_score(score),
                "added_at": item.created_at,
            }
        )
    return items


async def add_watchlist_item(
    session: AsyncSession,
    user_id: int,
    *,
    security_id: int | None = None,
    code: str | None = None,
    note: str | None = None,
) -> tuple[WatchlistItem, Security]:
    security: Security | None = None
    if security_id is not None:
        security = await session.get(Security, security_id)
    elif code:
        security = await get_security(session, code)
    if security is None:
        raise StockNotFoundError("security not found")

    existing = await session.scalar(
        select(WatchlistItem).where(
            WatchlistItem.user_id == user_id,
            WatchlistItem.security_id == security.id,
        )
    )
    if existing is not None:
        raise WatchlistDuplicateError("already in watchlist")

    item = WatchlistItem(user_id=user_id, security_id=security.id, note=note)
    session.add(item)
    await session.commit()
    await session.refresh(item)
    return item, security


async def update_watchlist_item(
    session: AsyncSession,
    user_id: int,
    security_id: int,
    *,
    note: str | None = None,
    sort_order: int | None = None,
) -> WatchlistItem | None:
    item = await session.scalar(
        select(WatchlistItem).where(
            WatchlistItem.user_id == user_id,
            WatchlistItem.security_id == security_id,
        )
    )
    if item is None:
        return None
    if note is not None:
        item.note = note
    if sort_order is not None:
        item.sort_order = sort_order
    await session.commit()
    await session.refresh(item)
    return item


async def remove_watchlist_item(session: AsyncSession, user_id: int, security_id: int) -> bool:
    item = await session.scalar(
        select(WatchlistItem).where(
            WatchlistItem.user_id == user_id,
            WatchlistItem.security_id == security_id,
        )
    )
    if item is None:
        return False
    await session.delete(item)
    await session.commit()
    return True


async def stock_detail(
    session: AsyncSession,
    user_id: int,
    code: str,
    *,
    scope: str = "all",
    window: str = "30d",
    limit: int = 20,
    use_llm_conclusion: bool = False,
) -> dict | None:
    security = await get_security(session, code)
    if security is None:
        return None

    pool = await load_report_pool(session, user_id, scope=scope, window=window)
    score = await compute_stock_score(
        session,
        user_id,
        security,
        scope=scope,
        window=window,
        pool=pool,
    )
    if use_llm_conclusion:
        from app.services.conclusions import enrich_detail_with_conclusion

        score = await enrich_detail_with_conclusion(session, user_id=user_id, score=score)
    entry_ids = {entry.report.id for entry in score.entries}
    related = [entry for entry in pool if entry.report.id in entry_ids][:limit]
    return {
        "security": {
            "id": security.id,
            "code": security.code,
            "symbol": security.symbol,
            "name": security.name,
            "exchange": security.exchange,
            "industry_code": security.industry_code,
            "aliases": security.aliases or [],
        },
        "score": serialize_stock_score(score),
        "related_reports": [
            serialize_report(entry.report, entry.author, entry.follow) for entry in related
        ],
    }
