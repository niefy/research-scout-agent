from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.analysis_graph import run_analysis
from app.core.config import settings
from app.models.job import LLMCallLog
from app.models.report import Report, ReportAnalysis
from app.models.security import Industry, Security

logger = logging.getLogger(__name__)


async def load_security_candidates(session: AsyncSession) -> tuple[list[dict], dict[str, str]]:
    rows = (
        await session.execute(
            select(Security.code, Security.name, Security.aliases, Security.industry_code).where(
                Security.enabled.is_(True)
            )
        )
    ).all()
    candidates = [
        {
            "code": code,
            "name": name,
            "aliases": aliases or [],
            "industry_code": industry_code,
        }
        for code, name, aliases, industry_code in rows
    ]

    industries = (
        await session.execute(
            select(Industry.name, Industry.code).where(Industry.enabled.is_(True))
        )
    ).all()
    return candidates, {name: code for name, code in industries}


async def analyze_pending(
    session: AsyncSession,
    *,
    limit: int = 50,
    report_ids: list[int] | None = None,
    force: bool = False,
) -> dict:
    stmt = select(Report).order_by(Report.published_at.desc()).limit(limit)
    if report_ids:
        stmt = select(Report).where(Report.id.in_(report_ids)).limit(limit)
    elif not force:
        stmt = stmt.where(Report.analysis_status.in_(("pending", "failed")))

    reports = list((await session.scalars(stmt)).all())
    candidates, industry_codes = await load_security_candidates(session)

    analyzed = 0
    failed = 0
    for report in reports:
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
    return {"analyzed": analyzed, "failed": failed, "candidates": len(reports)}


async def analyze_report(
    session: AsyncSession,
    report: Report,
    *,
    candidates: list[dict] | None = None,
    industry_codes: dict[str, str] | None = None,
    use_llm: bool | None = None,
) -> bool:
    if candidates is None or industry_codes is None:
        candidates, industry_codes = await load_security_candidates(session)

    try:
        analysis, meta, flags = await run_analysis(
            report_id=report.id,
            title=report.title,
            content=report.content or report.title,
            author_name=report.raw_author_name,
            source_name=report.source_name,
            published_at=report.published_at,
            candidate_securities=candidates,
            use_llm=settings.llm_enabled if use_llm is None else use_llm,
        )
    except Exception as exc:  # noqa: BLE001 - analysis failure is persisted on the report
        logger.exception("analysis failed for report %s", report.id)
        report.analysis_status = "failed"
        report.meta = {**(report.meta or {}), "analysis_error": str(exc)[:500]}
        await session.commit()
        return False

    # Only explicit industry mentions define an industry relation. Deriving
    # industries from mentioned stocks would fan a single-stock article out to
    # every peer in that industry.
    industry_code_set: set[str] = set()
    for mention in analysis.industry_mentions:
        code = industry_codes.get(mention.name)
        if code:
            industry_code_set.add(code)

    version = (
        await session.scalar(
            select(func.max(ReportAnalysis.version)).where(ReportAnalysis.report_id == report.id)
        )
    ) or 0
    record = ReportAnalysis(
        report_id=report.id,
        version=version + 1,
        prompt_version="v1",
        model=str(meta.get("model") or "heuristic"),
        primary_category=analysis.primary_category,
        categories=list(analysis.categories),
        score=analysis.score,
        confidence=analysis.confidence,
        direction=analysis.direction,
        horizon=analysis.horizon,
        summary=analysis.summary,
        opinion=analysis.opinion,
        key_points=list(analysis.key_points),
        keywords=list(analysis.keywords),
        stock_mentions=[mention.model_dump() for mention in analysis.stock_mentions],
        industry_mentions=[mention.model_dump() for mention in analysis.industry_mentions],
        macro_mentions=[mention.model_dump() for mention in analysis.macro_mentions],
        rationale=analysis.rationale,
        quality_flags=flags,
        raw_output=meta.get("raw_output") or {},
        input_tokens=int(meta.get("input_tokens") or 0),
        output_tokens=int(meta.get("output_tokens") or 0),
        latency_ms=int(meta.get("latency_ms") or 0),
    )
    session.add(record)
    await session.flush()

    report.primary_category = analysis.primary_category
    report.categories = list(analysis.categories)
    report.stock_codes = [m.code for m in analysis.stock_mentions if m.code]
    report.industry_codes = sorted(industry_code_set)
    report.macro_tags = [m.tag for m in analysis.macro_mentions]
    report.keywords = list(analysis.keywords)
    report.summary = analysis.summary
    report.opinion = analysis.opinion
    report.score = analysis.score
    report.confidence = analysis.confidence
    report.direction = analysis.direction
    report.horizon = analysis.horizon
    report.current_analysis_id = record.id
    report.analysis_status = "done"

    session.add(
        LLMCallLog(
            purpose="analyze",
            model=str(meta.get("model") or "heuristic"),
            report_id=report.id,
            success=True,
            fallback=bool(meta.get("fallback")),
            input_tokens=int(meta.get("input_tokens") or 0),
            output_tokens=int(meta.get("output_tokens") or 0),
            latency_ms=int(meta.get("latency_ms") or 0),
        )
    )
    await session.commit()
    return True


async def analysis_stats(session: AsyncSession) -> dict:
    total = await session.scalar(select(func.count(Report.id))) or 0
    done = await session.scalar(
        select(func.count(Report.id)).where(Report.analysis_status == "done")
    ) or 0
    failed = await session.scalar(
        select(func.count(Report.id)).where(Report.analysis_status == "failed")
    ) or 0
    return {"total": total, "done": done, "failed": failed, "pending": total - done - failed}


def today_start() -> datetime:
    now = datetime.now(UTC)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)
