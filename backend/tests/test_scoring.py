from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.core.constants import display_score
from app.scoring.feed import DiversityLimits, diversify, hot_score, hot_signal
from app.scoring.stock import ScoreInput, aggregate_scores, recency_factor


def _input(
    report_id: int,
    *,
    score: float = 0.5,
    confidence: float = 0.8,
    category: str = "stock",
    author_weight: float = 1.0,
    age_days: float = 0.0,
    relevance: float = 1.0,
) -> ScoreInput:
    return ScoreInput(
        report_id=report_id,
        title=f"report-{report_id}",
        category=category,
        score=score,
        confidence=confidence,
        author_weight=author_weight,
        published_at=datetime.now(UTC) - timedelta(days=age_days),
        relevance=relevance,
    )


def test_display_score_mapping():
    assert display_score(-1) == 0.0
    assert display_score(0) == 50.0
    assert display_score(1) == 100.0
    assert display_score(None) is None


def test_recency_factor_halves_after_one_half_life():
    now = datetime.now(UTC)
    factor = recency_factor(now - timedelta(days=7), now, half_life_days=7)
    assert factor == pytest.approx(0.5)


def test_more_reports_do_not_change_the_normalized_score():
    one = aggregate_scores([_input(1, score=0.8, confidence=0.9)])
    many = aggregate_scores([_input(i, score=0.8, confidence=0.9) for i in range(1, 11)])

    assert one.raw_score == pytest.approx(0.8)
    assert many.raw_score == pytest.approx(0.8)
    # Only the stock category is present, so it receives the full 100 points.
    assert one.total_points == pytest.approx(90.0)
    assert one.final_score == pytest.approx(many.final_score)
    assert one.n_eff < many.n_eff


def test_category_budgets_are_40_40_20():
    result = aggregate_scores(
        [
            _input(1, score=0.0, category="stock"),
            _input(2, score=0.0, category="industry"),
            _input(3, score=0.0, category="macro"),
        ]
    )
    scores = {item.category: item for item in result.category_scores}
    assert scores["stock"].budget_points == pytest.approx(40)
    assert scores["industry"].budget_points == pytest.approx(40)
    assert scores["macro"].budget_points == pytest.approx(20)
    # Neutral signals earn half of each budget.
    assert scores["stock"].points == pytest.approx(20)
    assert scores["industry"].points == pytest.approx(20)
    assert scores["macro"].points == pytest.approx(10)
    assert result.total_points == pytest.approx(50)
    assert result.final_score == pytest.approx(0)


def test_missing_categories_redistribute_their_budget():
    only_stock = aggregate_scores([_input(1, score=0.5, category="stock")])
    assert len(only_stock.category_scores) == 1
    stock = only_stock.category_scores[0]
    assert stock.budget_share == pytest.approx(1.0)
    assert stock.budget_points == pytest.approx(100)
    assert only_stock.total_points == pytest.approx(75)

    stock_and_macro = aggregate_scores(
        [
            _input(1, score=0.0, category="stock"),
            _input(2, score=0.0, category="macro"),
        ]
    )
    shares = {item.category: item.budget_share for item in stock_and_macro.category_scores}
    assert shares["stock"] == pytest.approx(2 / 3, abs=1e-3)
    assert shares["macro"] == pytest.approx(1 / 3, abs=1e-3)


def test_total_score_never_exceeds_100():
    result = aggregate_scores(
        [
            _input(1, score=1.0, category="stock"),
            _input(2, score=1.0, category="industry"),
            _input(3, score=1.0, category="macro"),
        ]
    )
    assert result.total_points == pytest.approx(100)
    assert result.final_score == pytest.approx(1)


def test_recent_reports_dominate_older_ones():
    now = datetime.now(UTC)
    result = aggregate_scores(
        [
            _input(1, score=1.0, age_days=0),
            _input(2, score=-1.0, age_days=30),
        ],
        now=now,
    )
    # Stock half-life is 7 days, so the 30-day-old bearish call is heavily decayed.
    assert result.category_scores[0].weighted_signal > 0.85


def test_reports_older_than_three_months_are_excluded():
    now = datetime.now(UTC)
    outside = aggregate_scores([_input(1, score=0.8, age_days=91)], now=now)
    assert outside.report_count == 0
    assert outside.total_points == 0

    inside = aggregate_scores([_input(2, score=0.8, age_days=89)], now=now)
    assert inside.report_count == 1


def test_aggregate_confidence_follows_report_confidence():
    weak = aggregate_scores([_input(1, score=0.6, confidence=0.2)])
    strong = aggregate_scores([_input(1, score=0.6, confidence=0.9)])
    assert strong.confidence > weak.confidence
    # With a single report, relative weights cancel before shrinkage.
    assert strong.final_score == pytest.approx(weak.final_score)


def test_aggregate_author_weight_shifts_mixed_signal():
    bullish_high = aggregate_scores(
        [
            _input(1, score=0.6, author_weight=4.0),
            _input(2, score=-0.6, author_weight=1.0),
        ]
    )
    bearish_high = aggregate_scores(
        [
            _input(1, score=0.6, author_weight=1.0),
            _input(2, score=-0.6, author_weight=4.0),
        ]
    )
    assert bullish_high.final_score > 0
    assert bearish_high.final_score < 0


def test_aggregate_ignores_zero_weight():
    result = aggregate_scores([_input(1, confidence=0.0)])
    assert result.report_count == 0
    assert result.final_score == 0.0


def test_hot_signal_bounds():
    assert hot_signal(None, None) == 0.5
    assert hot_signal(1.0, 1.0) == 1.0
    assert hot_signal(1.0, -1.0) == 1.0


def test_hot_score_prefers_fresh_and_strong():
    now = datetime.now(UTC)
    fresh = hot_score(
        default_weight=1.0,
        published_at=now - timedelta(hours=1),
        confidence=0.8,
        score=0.7,
        now=now,
    )
    stale = hot_score(
        default_weight=1.0,
        published_at=now - timedelta(days=5),
        confidence=0.8,
        score=0.7,
        now=now,
    )
    assert fresh > stale


def _row(row_id: int, author: int, cluster: int | None, category: str):
    return {"id": row_id, "author": author, "cluster": cluster, "category": category}


def test_diversify_deduplicates_clusters_and_caps_author():
    rows = [
        _row(1, 1, 10, "stock"),
        _row(2, 1, 11, "stock"),
        _row(3, 1, 12, "stock"),
        _row(4, 2, 13, "industry"),
    ]
    selected = diversify(
        rows,
        key_author=lambda r: r["author"],
        key_cluster=lambda r: r["cluster"],
        key_category=lambda r: r["category"],
        limit=3,
        limits=DiversityLimits(max_per_author=2, max_per_category=6, window=20),
    )
    ids = [row["id"] for row in selected]
    assert ids == [1, 2, 4]


def test_diversify_drops_duplicate_clusters():
    rows = [
        _row(1, 1, 99, "stock"),
        _row(2, 2, 99, "industry"),
        _row(3, 3, 100, "macro"),
    ]
    selected = diversify(
        rows,
        key_author=lambda r: r["author"],
        key_cluster=lambda r: r["cluster"],
        key_category=lambda r: r["category"],
        limit=10,
    )
    assert [row["id"] for row in selected] == [1, 3]
