from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.personalization import WatchlistItem
from app.models.security import Security, StockScoreSnapshot
from app.models.user import User

if TYPE_CHECKING:
    from app.services.stocks import StockScore


def _tz() -> ZoneInfo:
    return ZoneInfo(settings.timezone)


def local_day_start_utc(day: date | None = None) -> datetime:
    zone = _tz()
    if day is None:
        day = datetime.now(zone).date()
    local_start = datetime.combine(day, time.min, tzinfo=zone)
    return local_start.astimezone(UTC)


def local_day_bounds_utc(day: date | None = None) -> tuple[datetime, datetime]:
    zone = _tz()
    if day is None:
        day = datetime.now(zone).date()
    start = datetime.combine(day, time.min, tzinfo=zone).astimezone(UTC)
    end = datetime.combine(day, time.max, tzinfo=zone).astimezone(UTC)
    return start, end


def local_yesterday() -> date:
    return datetime.now(_tz()).date() - timedelta(days=1)


async def load_previous_snapshots(
    session: AsyncSession,
    user_id: int,
    security_ids: list[int],
    *,
    scope: str,
    window: str,
    before: datetime | None = None,
) -> dict[int, StockScoreSnapshot]:
    if not security_ids:
        return {}
    stmt = (
        select(StockScoreSnapshot)
        .where(
            StockScoreSnapshot.user_id == user_id,
            StockScoreSnapshot.security_id.in_(security_ids),
            StockScoreSnapshot.scope == scope,
            StockScoreSnapshot.window == window,
        )
        .order_by(StockScoreSnapshot.computed_at.desc())
        .limit(max(200, len(security_ids) * 20))
    )
    if before is not None:
        stmt = stmt.where(StockScoreSnapshot.computed_at < before)
    rows = list((await session.scalars(stmt)).all())
    previous: dict[int, StockScoreSnapshot] = {}
    for row in rows:
        previous.setdefault(row.security_id, row)
    return previous


def _snapshot_payload(score: StockScore, *, now: datetime) -> dict:
    return {
        "security_id": score.security.id,
        "scope": score.scope,
        "window": score.window,
        "report_count": score.result.report_count,
        "raw_score": score.result.raw_score,
        "final_score": score.result.final_score,
        "total_points": score.result.total_points,
        "qualitative_score": score.qualitative_score,
        "adjustment": score.result.adjustment,
        "n_eff": score.result.n_eff,
        "confidence": score.result.confidence,
        "conclusion": score.conclusion,
        "relation_counts": dict(score.result.relation_counts),
        "evidence_level": score.evidence.level,
        "evidence": score.evidence.as_dict(),
        "breakdown": {
            "report_ids": sorted(item.report_id for item in score.result.breakdown),
            "relation_counts": dict(score.result.relation_counts),
        },
        "computed_at": now,
    }


async def record_score_snapshot(
    session: AsyncSession,
    user_id: int,
    score: StockScore,
    *,
    min_interval: timedelta = timedelta(hours=1),
    commit: bool = True,
) -> StockScoreSnapshot | None:
    now = datetime.now(UTC)
    latest = await session.scalar(
        select(StockScoreSnapshot)
        .where(
            StockScoreSnapshot.user_id == user_id,
            StockScoreSnapshot.security_id == score.security.id,
            StockScoreSnapshot.scope == score.scope,
            StockScoreSnapshot.window == score.window,
        )
        .order_by(StockScoreSnapshot.computed_at.desc())
        .limit(1)
    )
    if latest is not None and now - latest.computed_at < min_interval:
        # Preserve a late LLM conclusion even when the numeric snapshot was
        # already written by the deterministic pass.
        if score.qualitative_score is not None and latest.qualitative_score is None:
            latest.conclusion = score.conclusion
            latest.qualitative_score = score.qualitative_score
            if commit:
                await session.commit()
        return latest

    snapshot = StockScoreSnapshot(user_id=user_id, **_snapshot_payload(score, now=now))
    session.add(snapshot)
    if commit:
        await session.commit()
        await session.refresh(snapshot)
    return snapshot


async def record_score_snapshots(
    session: AsyncSession,
    user_id: int,
    scores: list[StockScore],
    *,
    min_interval: timedelta = timedelta(hours=1),
) -> None:
    for score in scores:
        await record_score_snapshot(
            session,
            user_id,
            score,
            min_interval=min_interval,
            commit=False,
        )
    await session.commit()


async def list_score_history(
    session: AsyncSession,
    user_id: int,
    security_id: int,
    *,
    scope: str,
    window: str,
    days: int = 30,
    limit: int = 100,
) -> list[StockScoreSnapshot]:
    cutoff = datetime.now(UTC) - timedelta(days=max(1, days))
    return list(
        (
            await session.scalars(
                select(StockScoreSnapshot)
                .where(
                    StockScoreSnapshot.user_id == user_id,
                    StockScoreSnapshot.security_id == security_id,
                    StockScoreSnapshot.scope == scope,
                    StockScoreSnapshot.window == window,
                    StockScoreSnapshot.computed_at >= cutoff,
                )
                .order_by(StockScoreSnapshot.computed_at.asc())
                .limit(limit)
            )
        ).all()
    )


def history_deltas(
    snapshots: list[StockScoreSnapshot],
    *,
    now: datetime | None = None,
) -> dict[str, float | None]:
    if not snapshots:
        return {"1d": None, "7d": None, "30d": None}
    now = now or datetime.now(UTC)
    latest = snapshots[-1]

    def previous_at(days: int) -> StockScoreSnapshot | None:
        target = now - timedelta(days=days)
        candidates = [row for row in snapshots if row.computed_at <= target]
        return candidates[-1] if candidates else None

    result: dict[str, float | None] = {}
    for key, days in (("1d", 1), ("7d", 7), ("30d", 30)):
        base = previous_at(days)
        result[key] = (
            round(latest.total_points - base.total_points, 2)
            if base is not None
            else None
        )
    return result


async def snapshot_watchlist_scores(
    session: AsyncSession,
    *,
    user_id: int | None = None,
) -> dict:
    from app.services.feedback import load_excluded_report_ids_by_security
    from app.services.stocks import (
        compute_stock_score,
        load_report_pool,
        normalize_scope,
    )

    if user_id is not None:
        user_ids = [user_id]
    else:
        user_ids = list(
            (
                await session.scalars(
                    select(WatchlistItem.user_id).distinct().order_by(WatchlistItem.user_id)
                )
            ).all()
        )

    snapshotted = 0
    for current_user_id in user_ids:
        user = await session.get(User, current_user_id)
        if user is None:
            continue
        scope = normalize_scope(None, user)
        window = "30d"
        rows = (
            await session.execute(
                select(WatchlistItem, Security)
                .join(Security, WatchlistItem.security_id == Security.id)
                .where(WatchlistItem.user_id == current_user_id)
            )
        ).all()
        if not rows:
            continue
        pool = await load_report_pool(
            session, current_user_id, scope=scope, window=window
        )
        exclusions = await load_excluded_report_ids_by_security(
            session, current_user_id
        )
        for _item, security in rows:
            score = await compute_stock_score(
                session,
                current_user_id,
                security,
                scope=scope,
                window=window,
                pool=pool,
                excluded_report_ids=exclusions.get(security.id, set()),
            )
            snapshot = await record_score_snapshot(
                session,
                current_user_id,
                score,
                min_interval=timedelta(hours=20),
                commit=False,
            )
            if snapshot is not None:
                snapshotted += 1
        await session.commit()
    return {"users": len(user_ids), "snapshots": snapshotted}


async def latest_snapshot_for_security(
    session: AsyncSession,
    user_id: int,
    security_id: int,
    *,
    scope: str,
    window: str,
) -> StockScoreSnapshot | None:
    return await session.scalar(
        select(StockScoreSnapshot)
        .where(
            StockScoreSnapshot.user_id == user_id,
            StockScoreSnapshot.security_id == security_id,
            StockScoreSnapshot.scope == scope,
            StockScoreSnapshot.window == window,
        )
        .order_by(StockScoreSnapshot.computed_at.desc())
        .limit(1)
    )


__all__ = [
    "history_deltas",
    "latest_snapshot_for_security",
    "load_previous_snapshots",
    "local_day_bounds_utc",
    "local_day_start_utc",
    "local_yesterday",
    "record_score_snapshot",
    "record_score_snapshots",
    "snapshot_watchlist_scores",
]
