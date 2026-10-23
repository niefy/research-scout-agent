from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.personalization import ReportSecurityFeedback


async def set_report_feedback(
    session: AsyncSession,
    user_id: int,
    report_id: int,
    security_id: int,
    *,
    action: str = "irrelevant",
) -> ReportSecurityFeedback:
    feedback = await session.scalar(
        select(ReportSecurityFeedback).where(
            ReportSecurityFeedback.user_id == user_id,
            ReportSecurityFeedback.report_id == report_id,
            ReportSecurityFeedback.security_id == security_id,
        )
    )
    if feedback is None:
        feedback = ReportSecurityFeedback(
            user_id=user_id,
            report_id=report_id,
            security_id=security_id,
            action=action,
        )
        session.add(feedback)
    else:
        feedback.action = action
    await session.commit()
    await session.refresh(feedback)
    return feedback


async def remove_report_feedback(
    session: AsyncSession,
    user_id: int,
    report_id: int,
    security_id: int,
) -> bool:
    result = await session.execute(
        delete(ReportSecurityFeedback).where(
            ReportSecurityFeedback.user_id == user_id,
            ReportSecurityFeedback.report_id == report_id,
            ReportSecurityFeedback.security_id == security_id,
        )
    )
    await session.commit()
    return (result.rowcount or 0) > 0


async def load_excluded_report_ids(
    session: AsyncSession,
    user_id: int,
    security_id: int,
) -> set[int]:
    rows = await session.scalars(
        select(ReportSecurityFeedback.report_id).where(
            ReportSecurityFeedback.user_id == user_id,
            ReportSecurityFeedback.security_id == security_id,
            ReportSecurityFeedback.action == "irrelevant",
        )
    )
    return set(rows.all())


async def load_excluded_report_ids_by_security(
    session: AsyncSession,
    user_id: int,
) -> dict[int, set[int]]:
    rows = (
        await session.execute(
            select(
                ReportSecurityFeedback.security_id,
                ReportSecurityFeedback.report_id,
            ).where(
                ReportSecurityFeedback.user_id == user_id,
                ReportSecurityFeedback.action == "irrelevant",
            )
        )
    ).all()
    result: dict[int, set[int]] = {}
    for security_id, report_id in rows:
        result.setdefault(security_id, set()).add(report_id)
    return result


__all__ = [
    "load_excluded_report_ids",
    "load_excluded_report_ids_by_security",
    "remove_report_feedback",
    "set_report_feedback",
]
