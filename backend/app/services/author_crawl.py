from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.collectors.base import AuthorTarget, CredentialsMissingError, make_http_client
from app.collectors.registry import get_adapter
from app.core.config import settings
from app.db.session import async_session_factory
from app.models.author import Author, AuthorIdentity
from app.models.channel import Channel
from app.models.job import IngestRun
from app.models.personalization import AuthorFollow
from app.models.report import Report
from app.services.analysis import analyze_report, load_security_candidates
from app.services.ingest import ingest_item

logger = logging.getLogger(__name__)


@dataclass
class AuthorTargetSpec:
    author: Author
    channel: Channel
    target: AuthorTarget


async def candidate_authors(
    session: AsyncSession,
    author_ids: list[int] | None = None,
) -> list[Author]:
    """Authors we crawl: curated authors union every followed author."""
    followed = select(AuthorFollow.author_id)
    stmt = (
        select(Author)
        .where(
            Author.status == "active",
            Author.crawl_enabled.is_(True),
            or_(Author.is_curated.is_(True), Author.id.in_(followed)),
        )
        .order_by(Author.curated_rank.desc(), Author.id)
    )
    if author_ids:
        stmt = stmt.where(Author.id.in_(author_ids))
    return list((await session.scalars(stmt)).all())


async def select_author_targets(
    session: AsyncSession,
    author_ids: list[int] | None = None,
) -> list[AuthorTargetSpec]:
    authors = await candidate_authors(session, author_ids)
    if not authors:
        return []

    rows = (
        await session.execute(
            select(AuthorIdentity, Channel)
            .join(Channel, AuthorIdentity.channel_id == Channel.id)
            .where(
                AuthorIdentity.author_id.in_([author.id for author in authors]),
                Channel.enabled.is_(True),
            )
            .order_by(AuthorIdentity.id)
        )
    ).all()

    by_author: dict[int, list[tuple[AuthorIdentity, Channel]]] = {}
    for identity, channel in rows:
        by_author.setdefault(identity.author_id, []).append((identity, channel))

    specs: list[AuthorTargetSpec] = []
    seen: set[tuple[int, int]] = set()
    for author in authors:
        for identity, channel in by_author.get(author.id, []):
            key = (author.id, channel.id)
            if key in seen:
                continue
            try:
                adapter = get_adapter(channel.adapter_key)
            except KeyError:
                continue
            if not adapter.supports_author_feed:
                continue
            seen.add(key)
            specs.append(
                AuthorTargetSpec(
                    author=author,
                    channel=channel,
                    target=AuthorTarget(
                        external_id=identity.external_id,
                        display_name=identity.display_name or author.canonical_name,
                        profile_url=identity.profile_url,
                        meta={"author_id": author.id, "channel_id": channel.id},
                    ),
                )
            )
    return specs


async def _authors_with_identity(
    session: AsyncSession,
    author_ids: list[int],
) -> set[int]:
    if not author_ids:
        return set()
    rows = await session.scalars(
        select(AuthorIdentity.author_id).where(AuthorIdentity.author_id.in_(author_ids))
    )
    return set(rows.all())


async def crawl_author_targets(
    session: AsyncSession,
    *,
    author_ids: list[int] | None = None,
    limit: int | None = None,
    force: bool = False,
) -> dict:
    authors = await candidate_authors(session, author_ids)
    candidate_ids = [author.id for author in authors]
    usable_ids = await _authors_with_identity(session, candidate_ids)
    no_identity_ids = [author_id for author_id in candidate_ids if author_id not in usable_ids]

    now = datetime.now(UTC)
    min_interval = timedelta(minutes=max(1, settings.author_crawl_min_interval_minutes))
    if not author_ids:
        authors = authors[: max(1, settings.author_crawl_max_authors)]
    specs = await select_author_targets(session, [author.id for author in authors])

    if not force:
        fresh_ids = {
            author.id
            for author in authors
            if author.last_crawled_at is not None
            and now - author.last_crawled_at < min_interval
        }
        specs = [spec for spec in specs if spec.author.id not in fresh_ids]
    else:
        fresh_ids = set()

    # Authors with an identity but no enabled/author-capable channel cannot be
    # crawled; surface them the same way as authors without any identity.
    usable_target_ids = {spec.author.id for spec in specs}
    for author in authors:
        if author.id in usable_ids and author.id not in usable_target_ids:
            no_identity_ids.append(author.id)

    for author in authors:
        if author.id in no_identity_ids:
            author.crawl_status = "no_identity"
            author.crawl_error = None
    if no_identity_ids:
        await session.commit()

    item_limit = limit or settings.author_crawl_items_per_author
    runs: list[dict] = []
    for spec in specs:
        runs.append(
            await _crawl_one_target(
                session,
                spec,
                limit=item_limit,
            )
        )

    created_ids = [report_id for run in runs for report_id in run.pop("_created_ids", [])]

    return {
        "authors": len(authors),
        "candidate_authors": len(candidate_ids),
        "targets": len(specs),
        "skipped_fresh": len(fresh_ids),
        "no_identity": sorted(set(no_identity_ids)),
        "fetched": sum(run["fetched"] for run in runs),
        "created": sum(run["created"] for run in runs),
        "duplicated": sum(run["duplicated"] for run in runs),
        "failed": sum(run["failed"] for run in runs),
        "conflicts": sum(run["conflicts"] for run in runs),
        "created_report_ids": created_ids,
        "runs": runs,
    }


async def _crawl_one_target(
    session: AsyncSession,
    spec: AuthorTargetSpec,
    *,
    limit: int,
) -> dict:
    author = spec.author
    channel = spec.channel
    run = IngestRun(
        run_type="author_crawl",
        channel_id=channel.id,
        author_id=author.id,
        status="running",
        stats={},
    )
    session.add(run)
    await session.commit()

    stats = {"fetched": 0, "created": 0, "duplicated": 0, "failed": 0, "conflicts": 0}
    created_ids: list[int] = []
    error: str | None = None
    status = "ok"
    try:
        adapter = get_adapter(channel.adapter_key)
        async with make_http_client() as client:
            raw_items = await adapter.fetch_author(
                client,
                channel.config or {},
                spec.target,
                limit,
            )
        stats["fetched"] = len(raw_items)

        for raw in raw_items:
            try:
                result = await ingest_item(
                    session,
                    channel,
                    raw,
                    adapter.key,
                    target_author=author,
                )
                stats[result.outcome] += 1
                if result.author_conflict:
                    stats["conflicts"] += 1
                if result.outcome == "created" and result.report_id is not None:
                    created_ids.append(result.report_id)
            except Exception as exc:  # noqa: BLE001 - one bad post must not abort the timeline
                stats["failed"] += 1
                logger.warning(
                    "author ingest failed author=%s channel=%s: %s",
                    author.id,
                    channel.code,
                    exc,
                )

        author = await session.get(Author, author.id)
        if author is not None:
            author.last_crawled_at = datetime.now(UTC)
            author.crawl_status = "conflict" if stats["conflicts"] else "ok"
            author.crawl_error = None
        run = await session.get(IngestRun, run.id)
        if run is not None:
            run.status = "success"
            run.stats = stats
            run.finished_at = datetime.now(UTC)
        await session.commit()
    except Exception as exc:  # noqa: BLE001 - author failures are recorded, not raised
        await session.rollback()
        stats["failed"] += 1
        error = str(exc)[:500]
        status = (
            "credentials_missing"
            if isinstance(exc, CredentialsMissingError)
            else "error"
        )
        logger.exception(
            "author crawl failed author=%s channel=%s", author.id, channel.code
        )
        author = await session.get(Author, author.id)
        if author is not None:
            author.crawl_status = status
            author.crawl_error = error
            author.last_crawled_at = datetime.now(UTC)
        run = await session.get(IngestRun, run.id)
        if run is not None:
            run.status = "failed"
            run.stats = stats
            run.error = error
            run.finished_at = datetime.now(UTC)
        await session.commit()

    return {
        "author_id": author.id if author is not None else spec.author.id,
        "author_name": spec.author.canonical_name,
        "channel_code": channel.code,
        "status": status,
        "fetched": stats["fetched"],
        "created": stats["created"],
        "duplicated": stats["duplicated"],
        "failed": stats["failed"],
        "conflicts": stats["conflicts"],
        "error": error,
        "_created_ids": created_ids,
    }


async def analyze_author_reports(
    session: AsyncSession,
    report_ids: list[int],
) -> dict:
    if not report_ids:
        return {"analyzed": 0, "failed": 0, "candidates": 0}
    candidates, industry_codes = await load_security_candidates(session)

    analyzed = 0
    failed = 0
    for report_id in report_ids:
        report = await session.get(Report, report_id)
        if report is None:
            continue
        ok = await analyze_report(
            session,
            report,
            candidates=candidates,
            industry_codes=industry_codes,
        )
        if ok:
            analyzed += 1
        else:
            failed += 1
    return {"analyzed": analyzed, "failed": failed, "candidates": len(report_ids)}


async def backfill_author(author_id: int, limit: int | None = None) -> dict:
    """Crawl a newly followed author immediately and analyze the new posts.

    Runs in its own session because it is scheduled from a request's background
    task after the response has already been committed.
    """
    async with async_session_factory() as session:
        result = await crawl_author_targets(
            session,
            author_ids=[author_id],
            limit=limit or settings.author_crawl_items_per_author,
            force=True,
        )
        analysis = await analyze_author_reports(session, result["created_report_ids"])
    result["analysis"] = analysis
    return result


__all__ = [
    "AuthorTargetSpec",
    "analyze_author_reports",
    "backfill_author",
    "candidate_authors",
    "crawl_author_targets",
    "select_author_targets",
]
