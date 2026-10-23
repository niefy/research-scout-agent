from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from app.models.security import StockScoreSnapshot
from app.services.conclusions import get_cached_conclusion
from app.services.snapshots import (
    history_deltas,
    list_score_history,
    load_previous_snapshots,
    local_day_start_utc,
    record_score_snapshot,
)
from app.services.stocks import compute_stock_score
from tests.factories import (
    add_author,
    add_channel,
    add_report,
    add_security,
    add_user,
)


async def _score(db_session):
    channel = await add_channel(db_session, code="mock")
    user = await add_user(db_session)
    author = await add_author(db_session, name="张分析", is_curated=True)
    security = await add_security(db_session, code="600519.SH", name="贵州茅台")
    report = await add_report(
        db_session,
        channel,
        author=author,
        title="茅台渠道反馈积极",
        stock_mentions=[
            {"code": "600519.SH", "name": "贵州茅台", "sentiment": 0.5}
        ],
    )
    score = await compute_stock_score(db_session, user.id, security, scope="hybrid")
    return user, security, report, score


async def _snapshot_count(db_session, user_id: int, security_id: int) -> int:
    return (
        await db_session.scalar(
            select(func.count(StockScoreSnapshot.id)).where(
                StockScoreSnapshot.user_id == user_id,
                StockScoreSnapshot.security_id == security_id,
            )
        )
        or 0
    )


async def test_snapshot_deduplicates_within_the_min_interval(db_session):
    user, security, _report, score = await _score(db_session)

    first = await record_score_snapshot(db_session, user.id, score)
    second = await record_score_snapshot(db_session, user.id, score)

    assert first is not None
    assert second is not None
    assert first.id == second.id
    assert await _snapshot_count(db_session, user.id, security.id) == 1


async def test_snapshot_records_evidence_and_breakdown(db_session):
    user, security, report, score = await _score(db_session)

    snapshot = await record_score_snapshot(db_session, user.id, score)

    assert snapshot is not None
    assert snapshot.total_points == score.result.total_points
    assert snapshot.evidence_level == "direct"
    assert snapshot.relation_counts == {"stock": 1}
    assert snapshot.breakdown["report_ids"] == [report.id]


async def test_late_llm_conclusion_is_written_to_existing_snapshot(db_session):
    user, _security, _report, score = await _score(db_session)
    first = await record_score_snapshot(db_session, user.id, score)

    score.conclusion = "LLM 生成的结构化结论"
    score.qualitative_score = 0.35
    second = await record_score_snapshot(db_session, user.id, score)

    assert second is not None and first is not None
    assert second.id == first.id
    assert second.qualitative_score == 0.35
    assert second.conclusion == "LLM 生成的结构化结论"


async def test_previous_snapshot_only_reads_before_today(db_session):
    user, security, _report, score = await _score(db_session)
    previous = await record_score_snapshot(db_session, user.id, score)
    assert previous is not None
    previous.computed_at = local_day_start_utc() - timedelta(hours=2)
    await db_session.commit()

    found = await load_previous_snapshots(
        db_session,
        user.id,
        [security.id],
        scope="hybrid",
        window="30d",
        before=local_day_start_utc(),
    )

    assert found[security.id].id == previous.id

    after_today = await load_previous_snapshots(
        db_session,
        user.id,
        [security.id],
        scope="hybrid",
        window="30d",
        before=local_day_start_utc() - timedelta(days=1),
    )
    assert after_today == {}


async def test_history_is_ascending_and_deltas_use_older_points(db_session):
    user = await add_user(db_session)
    security = await add_security(db_session, code="600519.SH", name="贵州茅台")
    now = datetime.now(UTC)
    for days_ago, points in ((10, 50.0), (3, 60.0), (0, 80.0)):
        db_session.add(
            StockScoreSnapshot(
                user_id=user.id,
                security_id=security.id,
                scope="hybrid",
                window="30d",
                total_points=points,
                computed_at=now - timedelta(days=days_ago),
            )
        )
    await db_session.commit()

    history = await list_score_history(
        db_session, user.id, security.id, scope="hybrid", window="30d", days=30
    )
    deltas = history_deltas(history, now=now)

    assert [row.total_points for row in history] == [50.0, 60.0, 80.0]
    assert deltas["1d"] == 20.0
    assert deltas["7d"] == 30.0
    assert deltas["30d"] is None


async def test_llm_cache_ignores_deterministic_snapshots(db_session):
    user, security, report, score = await _score(db_session)
    snapshot = await record_score_snapshot(db_session, user.id, score)
    assert snapshot is not None

    cached = await get_cached_conclusion(
        db_session,
        user_id=user.id,
        security_id=security.id,
        scope="hybrid",
        window="30d",
        report_ids=[report.id],
    )
    assert cached is None

    snapshot.qualitative_score = 0.25
    snapshot.conclusion = "缓存结论"
    await db_session.commit()

    cached = await get_cached_conclusion(
        db_session,
        user_id=user.id,
        security_id=security.id,
        scope="hybrid",
        window="30d",
        report_ids=[report.id],
    )
    assert cached == ("缓存结论", 0.25)

    # A different report set must invalidate the cache.
    assert (
        await get_cached_conclusion(
            db_session,
            user_id=user.id,
            security_id=security.id,
            scope="hybrid",
            window="30d",
            report_ids=[report.id + 999],
        )
        is None
    )
