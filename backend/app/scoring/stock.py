from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.core.constants import (
    AGGREGATION_SHRINK_K,
    ALL_CATEGORIES,
    CATEGORY_BUDGET_WEIGHTS,
    DEFAULT_HALF_LIFE_DAYS,
    MAX_REPORT_AGE_DAYS,
    clamp,
)

TOTAL_POINTS = 100.0


@dataclass
class ScoreInput:
    report_id: int
    title: str
    category: str
    score: float
    confidence: float
    author_weight: float
    published_at: datetime
    relevance: float = 1.0


@dataclass
class BreakdownEntry:
    report_id: int
    title: str
    category: str
    score: float
    confidence: float
    author_weight: float
    category_weight: float
    recency_factor: float
    relevance: float
    effective_weight: float
    published_at: datetime


@dataclass
class CategoryScore:
    """Score contribution of one category (stock / industry / macro).

    ``budget_share`` is the effective share after redistributing categories
    that have no usable reports. ``points`` is always within
    ``[0, budget_points]``; a neutral weighted signal earns half the budget.
    """

    category: str
    budget_share: float
    budget_points: float
    article_count: int
    weighted_signal: float
    points: float
    weight_sum: float
    confidence: float


@dataclass
class AggregateResult:
    raw_score: float
    final_score: float
    total_points: float
    n_eff: float
    confidence: float
    adjustment: float = 0.0
    breakdown: list[BreakdownEntry] = field(default_factory=list)
    category_counts: dict[str, int] = field(default_factory=dict)
    category_scores: list[CategoryScore] = field(default_factory=list)

    @property
    def report_count(self) -> int:
        return len(self.breakdown)


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def age_days(published_at: datetime, now: datetime) -> float:
    return max(0.0, (as_utc(now) - as_utc(published_at)).total_seconds() / 86400.0)


def recency_factor(published_at: datetime, now: datetime, half_life_days: float) -> float:
    if half_life_days <= 0:
        return 1.0
    return 0.5 ** (age_days(published_at, now) / half_life_days)


def _normalized_budgets(category_weights: dict[str, float] | None) -> dict[str, float]:
    weights: dict[str, float] = {}
    for category in ALL_CATEGORIES:
        raw = CATEGORY_BUDGET_WEIGHTS[category]
        if category_weights and category in category_weights:
            raw = category_weights[category]
        weights[category] = max(0.0, float(raw))
    if sum(weights.values()) <= 0:
        return dict(CATEGORY_BUDGET_WEIGHTS)
    return weights


def aggregate_scores(
    items: list[ScoreInput],
    *,
    now: datetime | None = None,
    shrink_k: float = AGGREGATION_SHRINK_K,
    category_weights: dict[str, float] | None = None,
    half_life_days: dict[str, float] | None = None,
    max_age_days: float = MAX_REPORT_AGE_DAYS,
) -> AggregateResult:
    """Aggregate report-level signals into a 0-100 stock score.

    Algorithm:
    1. Drop reports older than ``max_age_days`` (90 days by default).
    2. Give every report a time-decayed weight:
       ``w = confidence × sqrt(author_weight) × relevance × 0.5^(age / half_life)``.
       Stock / industry / macro use 7 / 14 / 30 day half-lives, so newer
       reports dominate within each category.
    3. Within each category, compute the weighted signal
       ``s_c = Σ(w_i × score_i) / Σw_i`` in ``[-1, 1]``.
    4. Allocate 40 / 40 / 20 points across categories. Categories with no
       usable reports are removed and their budget is redistributed
       proportionally over the remaining ones.
    5. Convert each category signal to points:
       ``points_c = (s_c + 1) / 2 × budget_c``. A neutral signal earns half
       the budget; the three categories always sum to at most 100.
    """
    now = now or datetime.now(UTC)
    budgets = _normalized_budgets(category_weights)
    half_lives = {**DEFAULT_HALF_LIFE_DAYS, **(half_life_days or {})}

    all_rows: list[tuple[float, float, BreakdownEntry]] = []
    grouped: dict[str, list[tuple[float, float, BreakdownEntry]]] = {
        category: [] for category in ALL_CATEGORIES
    }
    category_counts: dict[str, int] = {}

    for item in items:
        if item.score is None or item.confidence is None:
            continue
        category = item.category if item.category in ALL_CATEGORIES else "macro"
        item_age = age_days(item.published_at, now)
        if max_age_days is not None and item_age > max_age_days:
            continue

        score = clamp(float(item.score))
        confidence = clamp(float(item.confidence), 0.0, 1.0)
        author_weight = max(0.0, float(item.author_weight or 0.0))
        relevance = max(0.0, min(1.0, float(item.relevance)))
        decay = recency_factor(item.published_at, now, half_lives.get(category, 14.0))
        effective = confidence * math.sqrt(author_weight) * relevance * decay
        if effective <= 0:
            continue

        entry = BreakdownEntry(
            report_id=item.report_id,
            title=item.title,
            category=category,
            score=round(score, 4),
            confidence=round(confidence, 4),
            author_weight=round(author_weight, 4),
            category_weight=0.0,
            recency_factor=round(decay, 4),
            relevance=round(relevance, 4),
            effective_weight=round(effective, 4),
            published_at=item.published_at,
        )
        row = (effective, effective * score, entry)
        all_rows.append(row)
        grouped[category].append(row)
        category_counts[category] = category_counts.get(category, 0) + 1

    total_weight = sum(row[0] for row in all_rows)
    if total_weight <= 0:
        return AggregateResult(
            raw_score=0.0,
            final_score=0.0,
            total_points=0.0,
            n_eff=0.0,
            confidence=0.0,
            category_counts=category_counts,
        )

    present = [category for category in ALL_CATEGORIES if grouped[category]]
    budget_total = sum(budgets[category] for category in present)
    if budget_total <= 0:
        present = list(ALL_CATEGORIES)
        budget_total = sum(CATEGORY_BUDGET_WEIGHTS.values())

    category_scores: list[CategoryScore] = []
    total_points = 0.0
    for category in present:
        rows = grouped[category]
        if not rows:
            continue
        weight_sum = sum(row[0] for row in rows)
        signal = sum(row[1] for row in rows) / weight_sum
        share = budgets[category] / budget_total
        budget_points = TOTAL_POINTS * share
        points = (signal + 1.0) / 2.0 * budget_points
        avg_confidence = sum(row[2].confidence * row[0] for row in rows) / weight_sum
        total_points += points

        for _, _, entry in rows:
            entry.category_weight = round(share, 4)

        category_scores.append(
            CategoryScore(
                category=category,
                budget_share=round(share, 4),
                budget_points=round(budget_points, 2),
                article_count=len(rows),
                weighted_signal=round(signal, 4),
                points=round(points, 2),
                weight_sum=round(weight_sum, 4),
                confidence=round(avg_confidence, 4),
            )
        )

    total_points = round(min(TOTAL_POINTS, max(0.0, total_points)), 2)
    raw_score = sum(row[1] for row in all_rows) / total_weight
    sum_sq = sum(row[0] ** 2 for row in all_rows)
    n_eff = (total_weight**2) / sum_sq if sum_sq > 0 else 0.0
    shrink = n_eff / (n_eff + shrink_k) if (n_eff + shrink_k) > 0 else 0.0
    avg_confidence = (
        sum(row[2].confidence * row[0] for row in all_rows) / total_weight
    )

    # Keep the legacy [-1, 1] representation aligned with the 0-100 total.
    final_score = clamp(total_points / (TOTAL_POINTS / 2.0) - 1.0)

    return AggregateResult(
        raw_score=round(raw_score, 4),
        final_score=round(final_score, 4),
        total_points=total_points,
        n_eff=round(n_eff, 4),
        confidence=round(clamp(shrink * avg_confidence, 0.0, 1.0), 4),
        breakdown=sorted(
            [row[2] for row in all_rows],
            key=lambda entry: entry.published_at,
            reverse=True,
        ),
        category_counts=category_counts,
        category_scores=category_scores,
    )
