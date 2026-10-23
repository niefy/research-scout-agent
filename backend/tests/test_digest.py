from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import delete, select, update

from app.core.config import settings
from app.models.author import Author
from app.models.personalization import (
    AuthorFollow,
    DigestDelivery,
    ReportInteraction,
    WatchlistItem,
)
from app.services.digest import build_digest
from app.services.digest_email import send_daily_digests
from app.services.email import EmailNotConfigured, render_digest_email
from app.services.snapshots import local_day_bounds_utc, local_yesterday
from tests.factories import (
    add_author,
    add_channel,
    add_report,
    add_security,
    add_user,
)


def _midday(day):
    start, end = local_day_bounds_utc(day)
    return start + (end - start) / 2


async def _digest_fixture(db_session, *, digest_email_enabled: bool = False):
    channel = await add_channel(db_session, code="mock")
    user = await add_user(db_session, digest_email_enabled=digest_email_enabled)
    followed = await add_author(
        db_session, name="关注作者", is_curated=True, curated_rank=1
    )
    recommended = await add_author(
        db_session, name="推荐作者", is_curated=True, curated_rank=9
    )
    db_session.add(AuthorFollow(user_id=user.id, author_id=followed.id))
    security = await add_security(db_session, code="600519.SH", name="贵州茅台")
    db_session.add(WatchlistItem(user_id=user.id, security_id=security.id))
    await db_session.commit()
    return channel, user, followed, recommended, security


async def test_digest_uses_local_day_boundaries(db_session):
    channel, user, followed, _recommended, _security = await _digest_fixture(
        db_session
    )
    today = local_yesterday() + timedelta(days=1)
    today_report = await add_report(
        db_session,
        channel,
        author=followed,
        title="今天的关注更新",
        published_at=_midday(today),
    )
    yesterday_report = await add_report(
        db_session,
        channel,
        author=followed,
        title="昨天的关注更新",
        published_at=_midday(today - timedelta(days=1)),
    )

    digest = await build_digest(db_session, user, digest_date=today)
    previous = await build_digest(
        db_session, user, digest_date=today - timedelta(days=1)
    )

    assert [item["id"] for item in digest["followed_updates"]] == [today_report.id]
    assert [item["id"] for item in previous["followed_updates"]] == [
        yesterday_report.id
    ]
    assert digest["date"] == today.isoformat()


async def test_digest_excludes_hidden_followed_updates(db_session):
    channel, user, followed, _recommended, _security = await _digest_fixture(
        db_session
    )
    today = local_yesterday() + timedelta(days=1)
    visible = await add_report(
        db_session,
        channel,
        author=followed,
        title="可见更新",
        published_at=_midday(today),
    )
    hidden = await add_report(
        db_session,
        channel,
        author=followed,
        title="已隐藏更新",
        published_at=_midday(today),
    )
    db_session.add(
        ReportInteraction(user_id=user.id, report_id=hidden.id, hidden=True)
    )
    await db_session.commit()

    digest = await build_digest(db_session, user, digest_date=today)

    assert [item["id"] for item in digest["followed_updates"]] == [visible.id]


async def test_digest_recommends_only_unfollowed_curated_authors(db_session):
    _channel, user, _followed, recommended, _security = await _digest_fixture(
        db_session
    )

    digest = await build_digest(db_session, user)

    ids = [author["id"] for author in digest["recommended_authors"]]
    assert ids == [recommended.id]


async def test_digest_reports_watchlist_evidence_gaps(db_session):
    channel, user, followed, _recommended, security = await _digest_fixture(
        db_session
    )
    today = local_yesterday() + timedelta(days=1)
    await add_report(
        db_session,
        channel,
        author=followed,
        title="茅台个股更新",
        published_at=_midday(today),
        stock_mentions=[
            {"code": security.code, "name": security.name, "sentiment": 0.6}
        ],
    )

    digest = await build_digest(db_session, user, digest_date=today)

    assert len(digest["watchlist_changes"]) == 1
    change = digest["watchlist_changes"][0]
    assert change["security"]["code"] == "600519.SH"
    assert change["evidence"]["level"] == "direct"
    assert "missing_industry" in change["evidence_gaps"]
    assert digest["evidence_gaps"] == [
        {
            "security": change["security"],
            "gaps": ["missing_industry"],
            "evidence_level": "direct",
        }
    ]
    assert digest["has_content"] is True


async def test_send_digest_raises_when_smtp_is_not_configured(
    db_session, monkeypatch
):
    _channel, user, _followed, _recommended, _security = await _digest_fixture(
        db_session, digest_email_enabled=True
    )
    monkeypatch.setattr(settings, "smtp_host", "")

    with pytest.raises(EmailNotConfigured):
        await send_daily_digests(db_session, user_id=user.id)


async def test_digest_email_is_idempotent(db_session, monkeypatch):
    channel, user, followed, _recommended, _security = await _digest_fixture(
        db_session, digest_email_enabled=True
    )
    yesterday = local_yesterday()
    await add_report(
        db_session,
        channel,
        author=followed,
        title="昨天的重要更新",
        published_at=_midday(yesterday),
    )
    sent: list[str] = []

    async def fake_send(to_email, subject, text, html):
        sent.append(to_email)

    monkeypatch.setattr(settings, "smtp_host", "smtp.example.com")
    monkeypatch.setattr("app.services.digest_email.send_email", fake_send)

    first = await send_daily_digests(db_session, user_id=user.id)
    second = await send_daily_digests(db_session, user_id=user.id)

    assert first["sent"] == 1
    assert second["sent"] == 0
    assert second["skipped"] == 1
    assert sent == [user.email]

    delivery = await db_session.scalar(
        select(DigestDelivery).where(
            DigestDelivery.user_id == user.id,
            DigestDelivery.digest_date == yesterday,
            DigestDelivery.channel == "email",
        )
    )
    assert delivery is not None
    assert delivery.status == "sent"


async def test_digest_email_skips_users_without_content(db_session, monkeypatch):
    _channel, user, _followed, _recommended, _security = await _digest_fixture(
        db_session, digest_email_enabled=True
    )
    # Remove follows, the watchlist and curation so the digest has no content.
    await db_session.execute(delete(AuthorFollow))
    await db_session.execute(delete(WatchlistItem))
    await db_session.execute(update(Author).values(is_curated=False))
    await db_session.commit()

    sent: list[str] = []

    async def fake_send(to_email, subject, text, html):
        sent.append(to_email)

    monkeypatch.setattr(settings, "smtp_host", "smtp.example.com")
    monkeypatch.setattr("app.services.digest_email.send_email", fake_send)

    stats = await send_daily_digests(
        db_session, digest_date=local_yesterday(), user_id=user.id
    )

    assert stats["sent"] == 0
    assert stats["skipped"] == 1
    assert sent == []


def test_email_escapes_external_titles():
    digest = {
        "date": "2026-10-18",
        "user": {"nickname": "<b>用户</b>"},
        "followed_updates": [
            {
                "author": {"name": "<img src=x>"},
                "title": "<script>alert(1)</script>",
            }
        ],
        "watchlist_changes": [],
        "evidence_gaps": [],
        "recommended_authors": [],
    }

    subject, text, html = render_digest_email(digest)

    assert "<script>" not in html
    assert "<img src=x>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "<script>" in text  # plain text is not HTML
    assert "2026-10-18" in subject
