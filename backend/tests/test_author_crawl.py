from __future__ import annotations

from sqlalchemy import select

from app.collectors.base import RawItem
from app.core.config import settings
from app.models.author import AuthorIdentity
from app.models.job import IngestRun
from app.models.personalization import AuthorFollow
from app.models.report import Report
from app.services import author_crawl
from app.services.ingest import ingest_item
from tests.factories import (
    add_author,
    add_channel,
    add_identity,
    add_user,
)


async def _follow(db_session, user_id: int, author_id: int) -> None:
    db_session.add(AuthorFollow(user_id=user_id, author_id=author_id))
    await db_session.commit()


async def test_crawl_targets_are_curated_union_followed(db_session):
    user = await add_user(db_session)
    channel = await add_channel(db_session, code="mock")
    curated = await add_author(db_session, name="精选作者", is_curated=True)
    followed = await add_author(db_session, name="关注作者")
    other = await add_author(db_session, name="其他作者")
    disabled = await add_author(
        db_session, name="停抓作者", crawl_enabled=False
    )
    inactive = await add_author(db_session, name="停用作者", status="inactive")

    await _follow(db_session, user.id, followed.id)
    await _follow(db_session, user.id, disabled.id)
    await _follow(db_session, user.id, inactive.id)

    for author in (curated, followed, other, disabled, inactive):
        await add_identity(
            db_session, author, channel, external_id=f"mock-author-{author.id}"
        )

    candidates = await author_crawl.candidate_authors(db_session)
    specs = await author_crawl.select_author_targets(db_session)

    assert {author.id for author in candidates} == {curated.id, followed.id}
    assert {spec.author.id for spec in specs} == {curated.id, followed.id}
    assert len(specs) == 2


async def test_target_selection_deduplicates_author_channel_pairs(db_session):
    user = await add_user(db_session)
    channel = await add_channel(db_session, code="mock")
    author = await add_author(db_session, name="关注作者")
    await _follow(db_session, user.id, author.id)
    await add_identity(db_session, author, channel, external_id="mock-1")
    await add_identity(db_session, author, channel, external_id="mock-2")

    specs = await author_crawl.select_author_targets(db_session)

    assert len(specs) == 1
    assert specs[0].author.id == author.id


async def test_authors_without_identity_are_marked_not_crawled(db_session):
    channel = await add_channel(db_session, code="mock")  # noqa: F841 - channel exists
    author = await add_author(db_session, name="无身份作者", is_curated=True)

    result = await author_crawl.crawl_author_targets(db_session)

    await db_session.refresh(author)
    assert result["targets"] == 0
    assert result["no_identity"] == [author.id]
    assert author.crawl_status == "no_identity"
    assert author.crawl_error is None


async def test_mock_author_crawl_creates_reports_and_records_run(db_session):
    user = await add_user(db_session)
    channel = await add_channel(db_session, code="mock", adapter_key="mock")
    author = await add_author(db_session, name="张分析")
    await add_identity(
        db_session, author, channel, external_id="mock-author-张分析"
    )
    await _follow(db_session, user.id, author.id)

    result = await author_crawl.crawl_author_targets(db_session, force=True)

    await db_session.refresh(author)
    assert result["fetched"] == 1
    assert result["created"] == 1
    assert result["runs"][0]["status"] == "ok"
    assert author.crawl_status == "ok"
    assert author.last_crawled_at is not None

    run = await db_session.scalar(
        select(IngestRun).where(IngestRun.run_type == "author_crawl")
    )
    assert run is not None
    assert run.author_id == author.id
    assert run.status == "success"

    second = await author_crawl.crawl_author_targets(db_session, force=True)
    assert second["created"] == 0
    assert second["duplicated"] == 1


async def test_ingest_keeps_existing_identity_on_conflict(db_session):
    channel = await add_channel(db_session, code="mock", adapter_key="mock")
    other = await add_author(db_session, name="已有作者")
    target = await add_author(db_session, name="目标作者")
    await add_identity(
        db_session, other, channel, external_id="mock-author-李产业"
    )

    raw = RawItem(
        external_id="post-1",
        url="https://example.com/post-1",
        title="半导体设备订单跟踪",
        content="行业订单继续增长。",
        author_name="李产业",
        author_external_id="mock-author-李产业",
    )

    result = await ingest_item(
        db_session, channel, raw, "mock", target_author=target
    )

    assert result.outcome == "created"
    assert result.author_conflict is True
    report = await db_session.get(Report, result.report_id)
    assert report is not None
    # The existing identity binding wins; the report is not silently rebound.
    assert report.author_id == other.id
    identity = await db_session.scalar(
        select(AuthorIdentity).where(
            AuthorIdentity.channel_id == channel.id,
            AuthorIdentity.external_id == "mock-author-李产业",
        )
    )
    assert identity is not None and identity.author_id == other.id


async def test_xueqiu_missing_cookie_fails_closed(db_session, monkeypatch):
    user = await add_user(db_session)
    channel = await add_channel(
        db_session,
        code="xueqiu",
        adapter_key="xueqiu",
        config={"author_only": True},
        secret_ref="XUEQIU_COOKIE",
    )
    author = await add_author(db_session, name="雪球作者")
    await add_identity(db_session, author, channel, external_id="123456")
    await _follow(db_session, user.id, author.id)
    monkeypatch.setattr(settings, "xueqiu_cookie", "")
    monkeypatch.delenv("XUEQIU_COOKIE", raising=False)

    result = await author_crawl.crawl_author_targets(db_session, force=True)

    await db_session.refresh(author)
    assert result["failed"] == 1
    assert result["runs"][0]["status"] == "credentials_missing"
    assert result["runs"][0]["error"]
    assert "cookie" in result["runs"][0]["error"].lower()
    assert author.crawl_status == "credentials_missing"


async def test_follow_backfills_only_on_first_follow(client, db_session, monkeypatch):
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "follow@example.com",
            "password": "password123",
            "nickname": "关注用户",
        },
    )
    assert response.status_code == 201, response.text
    token = response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    channel = await add_channel(db_session, code="mock")
    author = await add_author(db_session, name="张分析")
    await add_identity(
        db_session, author, channel, external_id="mock-author-张分析"
    )
    no_identity = await add_author(db_session, name="无身份作者")

    calls: list[int] = []

    async def fake_backfill(author_id: int) -> dict:
        calls.append(author_id)
        return {}

    monkeypatch.setattr("app.api.v1.authors.backfill_author", fake_backfill)

    first = await client.post(
        f"/api/v1/authors/{author.id}/follow", json={}, headers=headers
    )
    second = await client.post(
        f"/api/v1/authors/{author.id}/follow", json={}, headers=headers
    )
    no_identity_follow = await client.post(
        f"/api/v1/authors/{no_identity.id}/follow", json={}, headers=headers
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert no_identity_follow.status_code == 200
    assert calls == [author.id]


async def test_import_xueqiu_author_parses_profile_and_only_first_follow_backfills(
    client, db_session, monkeypatch
):
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "import@example.com",
            "password": "password123",
            "nickname": "导入用户",
        },
    )
    token = response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    await add_channel(
        db_session,
        code="xueqiu",
        adapter_key="xueqiu",
        config={"author_only": True},
        secret_ref="XUEQIU_COOKIE",
    )

    calls: list[int] = []

    async def fake_backfill(author_id: int) -> dict:
        calls.append(author_id)
        return {}

    monkeypatch.setattr("app.api.v1.authors.backfill_author", fake_backfill)

    first = await client.post(
        "/api/v1/authors/import",
        json={"profile_url": "https://xueqiu.com/u/987654", "display_name": "雪球博主"},
        headers=headers,
    )
    assert first.status_code == 201, first.text
    body = first.json()
    assert body["created"] is True
    assert body["followed"] is True
    assert body["backfill_scheduled"] is True

    second = await client.post(
        "/api/v1/authors/import",
        json={"external_id": "987654"},
        headers=headers,
    )
    assert second.status_code == 201, second.text
    assert second.json()["created"] is False
    assert second.json()["backfill_scheduled"] is False

    identity = await db_session.scalar(
        select(AuthorIdentity).where(AuthorIdentity.external_id == "987654")
    )
    assert identity is not None
    assert identity.author_id == body["author"]["id"]
    assert calls == [body["author"]["id"]]
