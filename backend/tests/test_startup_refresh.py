from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.models.job import IngestRun
from app.services import startup_refresh


async def _add_crawl_run(
    db_session,
    *,
    finished_minutes_ago: float | None,
    run_type: str = "crawl",
) -> None:
    now = datetime.now(UTC)
    finished_at = (
        None if finished_minutes_ago is None else now - timedelta(minutes=finished_minutes_ago)
    )
    db_session.add(
        IngestRun(
            run_type=run_type,
            status="success" if finished_at else "running",
            started_at=now - timedelta(minutes=5),
            finished_at=finished_at,
            stats={},
        )
    )
    await db_session.commit()


async def test_refresh_skips_when_last_crawl_is_recent(db_session, monkeypatch):
    await _add_crawl_run(db_session, finished_minutes_ago=20)
    await _add_crawl_run(
        db_session, finished_minutes_ago=20, run_type="author_crawl"
    )

    called = False

    async def fake_crawl(session):
        nonlocal called
        called = True
        return []

    monkeypatch.setattr(startup_refresh, "crawl_channels", fake_crawl)

    result = await startup_refresh.refresh_if_stale()

    assert result["skipped"] is True
    assert result["reason"] == "fresh"
    assert called is False


async def test_refresh_runs_when_last_crawl_is_older_than_one_hour(db_session, monkeypatch):
    await _add_crawl_run(db_session, finished_minutes_ago=90)

    calls: list[str] = []

    async def fake_crawl(session):
        calls.append("crawl")
        return [{"channel_code": "sina", "created": 0}]

    async def fake_analyze(session, *, limit):
        calls.append("analyze")
        assert limit > 0
        return {"analyzed": 0, "failed": 0, "candidates": 0}

    monkeypatch.setattr(startup_refresh, "crawl_channels", fake_crawl)
    monkeypatch.setattr(startup_refresh, "analyze_pending", fake_analyze)

    result = await startup_refresh.refresh_if_stale()

    assert result["skipped"] is False
    assert calls == ["crawl", "analyze"]
    assert result["crawl"] == [{"channel_code": "sina", "created": 0}]
    assert result["analysis"]["analyzed"] == 0


async def test_refresh_runs_when_no_crawl_has_completed(db_session, monkeypatch):
    called = False

    async def fake_crawl(session):
        nonlocal called
        called = True
        return []

    async def fake_analyze(session, *, limit):
        return {"analyzed": 0, "failed": 0, "candidates": 0}

    monkeypatch.setattr(startup_refresh, "crawl_channels", fake_crawl)
    monkeypatch.setattr(startup_refresh, "analyze_pending", fake_analyze)

    result = await startup_refresh.refresh_if_stale()

    assert result["skipped"] is False
    assert called is True


async def test_refresh_does_not_run_while_another_crawl_is_active(db_session, monkeypatch):
    await _add_crawl_run(db_session, finished_minutes_ago=None)
    monkeypatch.setattr(startup_refresh.settings, "author_crawl_enabled", False)

    called = False

    async def fake_crawl(session):
        nonlocal called
        called = True
        return []

    monkeypatch.setattr(startup_refresh, "crawl_channels", fake_crawl)

    result = await startup_refresh.refresh_if_stale()

    assert result["skipped"] is True
    assert result["reason"] == "crawl_in_progress"
    assert called is False
