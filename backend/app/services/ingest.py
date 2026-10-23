from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.collectors.base import RawItem, make_http_client
from app.collectors.registry import get_adapter
from app.core.config import settings
from app.models.author import Author, AuthorIdentity
from app.models.channel import Channel
from app.models.job import IngestRun
from app.models.report import Report, ReportCluster
from app.scoring.text import (
    clean_text,
    content_hash,
    hamming_distance,
    make_external_id,
    simhash64,
)
from app.services.authors import resolve_author

logger = logging.getLogger(__name__)

SIMHASH_REPRINT_THRESHOLD = 3
SIMHASH_LOOKBACK_DAYS = 14


@dataclass
class IngestResult:
    outcome: str
    report_id: int | None = None
    author_conflict: bool = False


async def crawl_channels(
    session: AsyncSession,
    *,
    channel_codes: list[str] | None = None,
    limit: int | None = None,
) -> list[dict]:
    stmt = select(Channel).where(Channel.enabled.is_(True))
    if channel_codes:
        stmt = stmt.where(Channel.code.in_(channel_codes))
    channels = list((await session.scalars(stmt.order_by(Channel.id))).all())

    results: list[dict] = []
    for channel in channels:
        adapter = get_adapter(channel.adapter_key)
        if not adapter.supports_channel_feed:
            results.append(
                {
                    "channel_code": channel.code,
                    "fetched": 0,
                    "created": 0,
                    "duplicated": 0,
                    "failed": 0,
                    "error": None,
                    "skipped": True,
                }
            )
            continue
        results.append(await ingest_channel(session, channel, limit=limit))
    return results


async def ingest_channel(
    session: AsyncSession,
    channel: Channel,
    *,
    limit: int | None = None,
) -> dict:
    adapter = get_adapter(channel.adapter_key)
    if not adapter.supports_channel_feed:
        return {
            "channel_code": channel.code,
            "fetched": 0,
            "created": 0,
            "duplicated": 0,
            "failed": 0,
            "error": None,
            "skipped": True,
        }

    run = IngestRun(run_type="crawl", channel_id=channel.id, status="running", stats={})
    session.add(run)
    await session.commit()

    stats = {"fetched": 0, "created": 0, "duplicated": 0, "failed": 0}
    error: str | None = None
    try:
        item_limit = limit or settings.crawl_max_items_per_channel
        async with make_http_client() as client:
            raw_items = await adapter.fetch(client, channel.config or {}, item_limit)
        stats["fetched"] = len(raw_items)

        for raw in raw_items:
            try:
                result = await ingest_item(session, channel, raw, adapter.key)
                stats[result.outcome] += 1
            except Exception as exc:  # noqa: BLE001 - one bad item must not stop the batch
                stats["failed"] += 1
                logger.warning(
                    "ingest item failed channel=%s url=%s: %s", channel.code, raw.url, exc
                )

        channel.last_cursor = {
            "last_run_at": datetime.now(UTC).isoformat(),
            "last_fetched": stats["fetched"],
            "last_created": stats["created"],
        }
        run.status = "success"
        run.stats = stats
        run.finished_at = datetime.now(UTC)
        await session.commit()
    except Exception as exc:  # noqa: BLE001 - channel failures are reported, not raised
        await session.rollback()
        error = str(exc)
        stats["failed"] += 1
        logger.exception("channel crawl failed: %s", channel.code)
        run = await session.get(IngestRun, run.id)
        if run is not None:
            run.status = "failed"
            run.stats = stats
            run.error = error[:2000]
            run.finished_at = datetime.now(UTC)
            await session.commit()

    return {
        "channel_code": channel.code,
        "fetched": stats["fetched"],
        "created": stats["created"],
        "duplicated": stats["duplicated"],
        "failed": stats["failed"],
        "error": error,
    }


async def ingest_item(
    session: AsyncSession,
    channel: Channel,
    raw: RawItem,
    adapter_key: str,
    *,
    target_author: Author | None = None,
) -> IngestResult:
    external_id = raw.external_id or make_external_id(raw.url, raw.title)
    existing = await session.scalar(
        select(Report).where(
            Report.channel_id == channel.id,
            Report.external_id == external_id,
        )
    )
    if existing is not None:
        return IngestResult("duplicated", report_id=existing.id)

    title = clean_text(raw.title)
    content = clean_text(raw.content)
    digest = content_hash(title, content)
    fingerprint = simhash64(f"{title}\n{content}")

    same_channel = await session.scalar(
        select(Report).where(
            Report.channel_id == channel.id,
            Report.content_hash == digest,
        )
    )
    if same_channel is not None:
        return IngestResult("duplicated", report_id=same_channel.id)

    reprint_of = await _find_reprint(session, digest, fingerprint, channel.id)
    published_at = raw.normalized_published_at()

    author_conflict = False
    if target_author is not None:
        author, author_conflict = await _resolve_target_author(
            session, channel, raw, target_author
        )
    else:
        author = await resolve_author(
            session,
            channel_id=channel.id,
            raw_name=raw.author_name,
            external_id=raw.author_external_id,
            profile_url=raw.author_profile_url,
        )

    report = Report(
        channel_id=channel.id,
        external_id=external_id,
        url=raw.url,
        title=title,
        content=content,
        author_id=author.id if author else None,
        raw_author_name=raw.author_name,
        source_name=raw.source_name or raw.author_name,
        published_at=published_at,
        content_hash=digest,
        simhash=fingerprint,
        engagement=raw.engagement or {},
        meta={**(raw.meta or {}), "adapter": adapter_key},
    )
    session.add(report)
    await session.flush()

    if reprint_of is not None:
        await _attach_to_cluster(session, reprint_of, report)

    await session.commit()
    return IngestResult(
        "created", report_id=report.id, author_conflict=author_conflict
    )


async def _resolve_target_author(
    session: AsyncSession,
    channel: Channel,
    raw: RawItem,
    target: Author,
) -> tuple[Author, bool]:
    """Resolve an author for a targeted crawl without fuzzy matching.

    The identity binding is authoritative. If it already points at a different
    author we keep the existing binding and report a conflict instead of
    silently rebinding or merging authors.
    """
    external_id = (raw.author_external_id or "").strip()
    if not external_id:
        return target, False

    identity = await session.scalar(
        select(AuthorIdentity).where(
            AuthorIdentity.channel_id == channel.id,
            AuthorIdentity.external_id == external_id,
        )
    )
    if identity is None:
        session.add(
            AuthorIdentity(
                author_id=target.id,
                channel_id=channel.id,
                external_id=external_id,
                display_name=raw.author_name or target.canonical_name,
                profile_url=raw.author_profile_url,
            )
        )
        return target, False

    if identity.author_id == target.id:
        if raw.author_name:
            identity.display_name = raw.author_name
        if raw.author_profile_url:
            identity.profile_url = raw.author_profile_url
        return target, False

    existing = await session.get(Author, identity.author_id)
    if existing is None:
        return target, False
    logger.warning(
        "author identity conflict channel=%s external_id=%s target=%s existing=%s",
        channel.code,
        external_id,
        target.id,
        existing.id,
    )
    return existing, True


async def _find_reprint(
    session: AsyncSession,
    digest: str,
    fingerprint: str,
    channel_id: int,
) -> Report | None:
    exact = await session.scalar(
        select(Report)
        .where(Report.content_hash == digest, Report.channel_id != channel_id)
        .order_by(Report.published_at.desc())
        .limit(1)
    )
    if exact is not None:
        return exact

    cutoff = datetime.now(UTC) - timedelta(days=SIMHASH_LOOKBACK_DAYS)
    candidates = (
        await session.scalars(
            select(Report)
            .where(Report.published_at >= cutoff, Report.simhash.is_not(None))
            .order_by(Report.published_at.desc())
            .limit(800)
        )
    ).all()

    best: tuple[int, Report] | None = None
    for candidate in candidates:
        if not candidate.simhash:
            continue
        distance = hamming_distance(fingerprint, candidate.simhash)
        if distance <= SIMHASH_REPRINT_THRESHOLD:
            if best is None or distance < best[0]:
                best = (distance, candidate)
    return best[1] if best else None


async def _attach_to_cluster(
    session: AsyncSession,
    original: Report,
    duplicate: Report,
) -> None:
    cluster: ReportCluster | None = None
    if original.cluster_id:
        cluster = await session.get(ReportCluster, original.cluster_id)
    if cluster is None:
        cluster = ReportCluster(
            canonical_report_id=original.id,
            simhash=original.simhash,
            size=1,
        )
        session.add(cluster)
        await session.flush()
        original.cluster_id = cluster.id

    cluster.size += 1
    original.reprint_count += 1
    duplicate.cluster_id = cluster.id
    duplicate.is_reprint = True
    duplicate.reprint_count = 0
