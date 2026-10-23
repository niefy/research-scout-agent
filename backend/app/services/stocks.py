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
POOL_LIMIT = 3000
ALLOWED_SCOPES = ("personal", "hybrid", "all")
DEFAULT_SCOPE = "hybrid"

WINDOW_LABELS = {"7d": "7天", "30d": "30天", "90d": "3个月", "all": "3个月"}
RELATION_LABELS = {"stock": "个股", "industry": "行业", "macro": "宏观"}


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


@dataclass(frozen=True)
class MatchResult:
    relation: str
    reason: str
    score: float
    relevance: float


@dataclass(frozen=True)
class Evidence:
    level: str
    label: str
    stock_count: int
    industry_count: int
    macro_count: int
    distinct_authors: int
    coverage: dict[str, bool]
    is_macro_only: bool
    is_insufficient: bool

    def as_dict(self) -> dict:
        return {
            "level": self.level,
            "label": self.label,
            "stock_count": self.stock_count,
            "industry_count": self.industry_count,
            "macro_count": self.macro_count,
            "distinct_authors": self.distinct_authors,
            "coverage": self.coverage,
            "is_macro_only": self.is_macro_only,
            "is_insufficient": self.is_insufficient,
        }


@dataclass
class StockScore:
    security: Security
    scope: str
    window: str
    result: AggregateResult
    entries: list[PoolEntry]
    conclusion: str
    display_score: float | None
    display_label: str
    evidence: Evidence
    relation_weights: dict[str, float]
    half_life_days: dict[str, float]
    qualitative_score: float | None = None
    previous_total_points: float | None = None
    delta_since: datetime | None = None
    source_scope: str = DEFAULT_SCOPE

    @property
    def report_count(self) -> int:
        return self.result.report_count

    @property
    def delta_points(self) -> float | None:
        if self.previous_total_points is None or self.display_score is None:
            return None
        return round(self.result.total_points - self.previous_total_points, 2)


def normalize_scope(scope: str | None, user: User | None = None) -> str:
    value = (scope or "").strip().lower()
    if value == "followed":
        value = "personal"
    if value in ALLOWED_SCOPES:
        return value
    configured = ((user.scoring_config if user else {}) or {}).get("default_scope")
    if configured in ALLOWED_SCOPES:
        return configured
    return DEFAULT_SCOPE


def _scoring_config(user: User | None) -> tuple[dict[str, float], dict[str, float]]:
    config = (user.scoring_config if user else {}) or {}
    raw_weights = config.get("relation_weights") or config.get("category_weights") or {}
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
    days = min(
        WINDOW_DELTAS.get(window, WINDOW_DELTAS["30d"]), int(MAX_REPORT_AGE_DAYS)
    )
    return datetime.now(UTC) - timedelta(days=days)


async def load_report_pool(
    session: AsyncSession,
    user_id: int,
    *,
    scope: str = DEFAULT_SCOPE,
    window: str = "30d",
) -> list[PoolEntry]:
    scope = normalize_scope(scope)
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
    followed_ids = select(AuthorFollow.author_id).where(
        AuthorFollow.user_id == user_id
    )
    if scope == "personal":
        stmt = stmt.where(Report.author_id.in_(followed_ids))
    elif scope == "hybrid":
        curated_ids = select(Author.id).where(
            Author.is_curated.is_(True), Author.status == "active"
        )
        stmt = stmt.where(
            or_(
                Report.author_id.in_(followed_ids),
                Report.author_id.in_(curated_ids),
            )
        )
    if cutoff is not None:
        stmt = stmt.where(Report.published_at >= cutoff)
    stmt = stmt.order_by(Report.published_at.desc()).limit(POOL_LIMIT)

    rows = (await session.execute(stmt)).all()
    return [
        PoolEntry(report=report, author=author, follow=follow, analysis=analysis)
        for report, author, follow, analysis in rows
    ]


def _match_report(entry: PoolEntry, security: Security) -> MatchResult | None:
    """Return the single strongest relation of a report to a security.

    Priority is stock > industry > macro. Because the function returns at most
    one result, an article can never count twice for the same stock.
    """
    report = entry.report
    code = security.code.upper()

    mentions = entry.analysis.stock_mentions if entry.analysis else []
    for mention in mentions:
        mention_code = str(mention.get("code") or "").upper()
        if mention_code == code:
            sentiment = float(mention.get("sentiment") or 0.0)
            score = (
                sentiment if abs(sentiment) >= 0.05 else float(report.score or 0.0)
            )
            relevance = max(
                0.5, min(1.0, float(mention.get("relevance") or 0.8))
            )
            return MatchResult(
                relation="stock",
                reason="direct_mention",
                score=score,
                relevance=relevance,
            )

    if code in {str(item).upper() for item in (report.stock_codes or [])}:
        return MatchResult(
            relation="stock",
            reason="stock_code_fallback",
            score=float(report.score or 0.0),
            relevance=0.7,
        )

    if security.industry_code and security.industry_code in (
        report.industry_codes or []
    ):
        return MatchResult(
            relation="industry",
            reason="industry_code",
            score=float(report.score or 0.0),
            relevance=0.75,
        )

    categories = report.categories or []
    has_macro_mention = bool(entry.analysis.macro_mentions) if entry.analysis else False
    if (
        report.primary_category == "macro"
        or "macro" in categories
        or has_macro_mention
    ):
        return MatchResult(
            relation="macro",
            reason="macro",
            score=float(report.score or 0.0),
            relevance=0.45,
        )

    return None


def _build_evidence(relation_counts: dict[str, int], distinct_authors: int) -> Evidence:
    stock_count = int(relation_counts.get("stock", 0))
    industry_count = int(relation_counts.get("industry", 0))
    macro_count = int(relation_counts.get("macro", 0))
    if stock_count > 0:
        level, label = "direct", "个股证据"
    elif industry_count > 0:
        level, label = "industry", "行业参考"
    elif macro_count > 0:
        level, label = "macro", "宏观参考"
    else:
        level, label = "none", "证据不足"
    return Evidence(
        level=level,
        label=label,
        stock_count=stock_count,
        industry_count=industry_count,
        macro_count=macro_count,
        distinct_authors=distinct_authors,
        coverage={
            "stock": stock_count > 0,
            "industry": industry_count > 0,
            "macro": macro_count > 0,
        },
        is_macro_only=level == "macro",
        is_insufficient=level in {"macro", "none"},
    )


def _build_conclusion(
    security: Security,
    result: AggregateResult,
    window: str,
    evidence: Evidence,
) -> str:
    if result.report_count == 0:
        return f"{security.name}暂无足够的相关分析，建议关注更多相关作者或等待新报告。"

    if evidence.level == "macro":
        stance = (
            "宏观信号偏多"
            if result.final_score >= 0.15
            else "宏观信号偏空"
            if result.final_score <= -0.15
            else "宏观信号中性"
        )
    else:
        stance = (
            "综合信号偏多"
            if result.final_score >= 0.15
            else "综合信号偏空"
            if result.final_score <= -0.15
            else "综合信号中性"
        )

    counts = result.relation_counts
    count_text = "、".join(
        f"{RELATION_LABELS[key]}{counts.get(key, 0)}条"
        for key in ("stock", "industry", "macro")
        if counts.get(key, 0)
    )
    breakdown_text = "、".join(
        f"{RELATION_LABELS[item.relation]}{item.points:.0f}/{item.budget_points:.0f}"
        for item in result.relation_scores
    )
    confidence_text = "证据较集中" if result.n_eff < 3 else "信源相对分散"
    top = sorted(
        result.breakdown,
        key=lambda item: item.effective_weight * abs(item.score),
        reverse=True,
    )[:2]
    top_text = ""
    if top:
        top_text = "；主要驱动：" + "、".join(
            f"《{item.title[:28]}》" for item in top
        )

    window_label = WINDOW_LABELS.get(window, window)
    score_text = f"{evidence.label}{result.total_points:.0f}/100"
    tail = f"{confidence_text}{top_text}"
    if evidence.level == "macro":
        tail = f"缺少个股与行业证据，不构成个股综合结论；{tail}"
    elif evidence.level == "industry":
        tail = f"当前缺少个股直接证据；{tail}"
    return (
        f"{security.name}近{window_label}纳入{result.report_count}条相关报告（{count_text}），"
        f"{stance}，{score_text}。关系构成：{breakdown_text}；{tail}"
    )


def _score_entries(
    security: Security,
    pool: list[PoolEntry],
    *,
    user: User | None,
    scope: str,
    window: str,
    excluded_report_ids: set[int] | None = None,
) -> StockScore:
    relation_weights, half_lives = _scoring_config(user)
    excluded = excluded_report_ids or set()
    matched: list[tuple[PoolEntry, MatchResult]] = []
    for entry in pool:
        if entry.report.id in excluded:
            continue
        match = _match_report(entry, security)
        if match is None:
            continue
        matched.append((entry, match))

    score_inputs = [
        ScoreInput(
            report_id=entry.report.id,
            title=entry.report.title,
            relation=match.relation,
            reason=match.reason,
            score=match.score,
            confidence=float(entry.report.confidence or 0.0),
            author_weight=(
                entry.follow.weight
                if entry.follow
                else (entry.author.default_weight if entry.author else 0.5)
            ),
            published_at=entry.report.published_at,
            relevance=match.relevance,
        )
        for entry, match in matched
    ]
    result = aggregate_scores(
        score_inputs,
        relation_weights=relation_weights,
        half_life_days=half_lives,
        max_age_days=MAX_REPORT_AGE_DAYS,
    )
    included_ids = {item.report_id for item in result.breakdown}
    included_entries = [
        entry for entry, _ in matched if entry.report.id in included_ids
    ]
    author_keys = {
        entry.author.id
        if entry.author
        else (entry.report.raw_author_name or f"report:{entry.report.id}")
        for entry in included_entries
    }
    evidence = _build_evidence(result.relation_counts, len(author_keys))
    conclusion = _build_conclusion(security, result, window, evidence)
    display_label = (
        "宏观参考"
        if evidence.level == "macro"
        else "证据不足"
        if evidence.level == "none"
        else "综合得分"
    )
    return StockScore(
        security=security,
        scope=scope,
        window=window,
        result=result,
        entries=included_entries,
        conclusion=conclusion,
        display_score=(
            result.total_points if evidence.level not in {"none"} else None
        ),
        display_label=display_label,
        evidence=evidence,
        relation_weights=relation_weights,
        half_life_days=half_lives,
        source_scope=scope,
    )


async def compute_stock_score(
    session: AsyncSession,
    user_id: int,
    security: Security,
    *,
    scope: str = DEFAULT_SCOPE,
    window: str = "30d",
    pool: list[PoolEntry] | None = None,
    excluded_report_ids: set[int] | None = None,
) -> StockScore:
    user = await session.get(User, user_id)
    resolved_scope = normalize_scope(scope, user)
    pool = (
        pool
        if pool is not None
        else await load_report_pool(
            session, user_id, scope=resolved_scope, window=window
        )
    )
    if excluded_report_ids is None:
        from app.services.feedback import load_excluded_report_ids

        excluded_report_ids = await load_excluded_report_ids(
            session, user_id, security.id
        )
    return _score_entries(
        security,
        pool,
        user=user,
        scope=resolved_scope,
        window=window,
        excluded_report_ids=excluded_report_ids,
    )


def serialize_stock_score(score: StockScore) -> dict:
    result = score.result
    entries_by_id = {entry.report.id: entry for entry in score.entries}
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
        "display_label": score.display_label,
        "n_eff": result.n_eff,
        "confidence": result.confidence,
        "conclusion": score.conclusion,
        "evidence": score.evidence.as_dict(),
        "relation_scores": [
            {
                "relation": item.relation,
                "budget_share": item.budget_share,
                "budget_points": item.budget_points,
                "article_count": item.article_count,
                "weighted_signal": item.weighted_signal,
                "points": item.points,
                "weight_sum": item.weight_sum,
                "confidence": item.confidence,
            }
            for item in result.relation_scores
        ],
        "relation_counts": result.relation_counts,
        "relation_weights": score.relation_weights,
        "half_life_days": score.half_life_days,
        "max_age_days": MAX_REPORT_AGE_DAYS,
        "breakdown": [
            {
                "report_id": item.report_id,
                "title": item.title,
                "relation": item.relation,
                "relation_reason": item.reason,
                "score": item.score,
                "confidence": item.confidence,
                "author_weight": item.author_weight,
                "relation_weight": item.relation_weight,
                "recency_factor": item.recency_factor,
                "relevance": item.relevance,
                "effective_weight": item.effective_weight,
                "published_at": item.published_at,
                "author_name": (
                    entries_by_id[item.report_id].author.canonical_name
                    if entries_by_id.get(item.report_id)
                    and entries_by_id[item.report_id].author
                    else (
                        entries_by_id[item.report_id].report.raw_author_name
                        if entries_by_id.get(item.report_id)
                        else None
                    )
                ),
                "source_name": (
                    entries_by_id[item.report_id].report.source_name
                    if entries_by_id.get(item.report_id)
                    else None
                ),
            }
            for item in result.breakdown
        ],
        "previous_total_points": score.previous_total_points,
        "score_delta": score.delta_points,
        "delta_since": score.delta_since,
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
    scope: str = DEFAULT_SCOPE,
    window: str = "30d",
) -> list[dict]:
    from app.services.feedback import load_excluded_report_ids_by_security
    from app.services.snapshots import (
        load_previous_snapshots,
        local_day_start_utc,
        record_score_snapshots,
    )

    user = await session.get(User, user_id)
    resolved_scope = normalize_scope(scope, user)
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

    pool = await load_report_pool(
        session, user_id, scope=resolved_scope, window=window
    )
    exclusions = await load_excluded_report_ids_by_security(session, user_id)
    previous = await load_previous_snapshots(
        session,
        user_id,
        [security.id for _, security in rows],
        scope=resolved_scope,
        window=window,
        before=local_day_start_utc(),
    )
    scores: list[StockScore] = []
    items = []
    for item, security in rows:
        score = await compute_stock_score(
            session,
            user_id,
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
        scores.append(score)
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
    await record_score_snapshots(
        session, user_id, scores, min_interval=timedelta(hours=1)
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


async def remove_watchlist_item(
    session: AsyncSession, user_id: int, security_id: int
) -> bool:
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
    scope: str = DEFAULT_SCOPE,
    window: str = "30d",
    limit: int = 20,
    use_llm_conclusion: bool = False,
) -> dict | None:
    from app.services.feedback import load_excluded_report_ids
    from app.services.snapshots import (
        load_previous_snapshots,
        local_day_start_utc,
        record_score_snapshot,
    )

    security = await get_security(session, code)
    if security is None:
        return None

    user = await session.get(User, user_id)
    resolved_scope = normalize_scope(scope, user)
    pool = await load_report_pool(
        session, user_id, scope=resolved_scope, window=window
    )
    excluded = await load_excluded_report_ids(session, user_id, security.id)
    previous = await load_previous_snapshots(
        session,
        user_id,
        [security.id],
        scope=resolved_scope,
        window=window,
        before=local_day_start_utc(),
    )
    score = await compute_stock_score(
        session,
        user_id,
        security,
        scope=resolved_scope,
        window=window,
        pool=pool,
        excluded_report_ids=excluded,
    )
    prior = previous.get(security.id)
    if prior is not None:
        score.previous_total_points = prior.total_points
        score.delta_since = prior.computed_at
    if use_llm_conclusion:
        from app.services.conclusions import enrich_detail_with_conclusion

        score = await enrich_detail_with_conclusion(
            session, user_id=user_id, score=score
        )
    await record_score_snapshot(
        session, user_id, score, min_interval=timedelta(hours=1)
    )

    breakdown_by_id = {item.report_id: item for item in score.result.breakdown}
    related = []
    for entry in score.entries[:limit]:
        data = serialize_report(entry.report, entry.author, entry.follow)
        item = breakdown_by_id.get(entry.report.id)
        if item is not None:
            data["relation"] = item.relation
            data["relation_reason"] = item.reason
        related.append(data)
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
        "related_reports": related,
    }
