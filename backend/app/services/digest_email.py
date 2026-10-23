from __future__ import annotations

import logging
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.personalization import DigestDelivery
from app.models.user import User
from app.services.digest import build_digest
from app.services.email import (
    EmailNotConfigured,
    render_digest_email,
    send_email,
)
from app.services.snapshots import local_yesterday

logger = logging.getLogger(__name__)


async def send_daily_digests(
    session: AsyncSession,
    *,
    digest_date: date | None = None,
    user_id: int | None = None,
) -> dict:
    if not settings.digest_email_enabled:
        return {
            "users": 0,
            "sent": 0,
            "skipped": 0,
            "failed": 0,
            "skipped_reason": "digest_email_disabled",
        }
    if not settings.smtp_host:
        raise EmailNotConfigured("SMTP_HOST is not configured")

    digest_date = digest_date or local_yesterday()

    stmt = select(User.id).where(
        User.status == "active",
        User.digest_email_enabled.is_(True),
        User.email.is_not(None),
        User.email != "",
    )
    if user_id is not None:
        stmt = stmt.where(User.id == user_id)
    user_ids = list((await session.scalars(stmt.order_by(User.id))).all())

    stats = {"users": len(user_ids), "sent": 0, "skipped": 0, "failed": 0}
    for current_user_id in user_ids:
        user = await session.get(User, current_user_id)
        if user is None:
            continue
        delivery = await session.scalar(
            select(DigestDelivery).where(
                DigestDelivery.user_id == current_user_id,
                DigestDelivery.digest_date == digest_date,
                DigestDelivery.channel == "email",
            )
        )
        if delivery is not None and delivery.status == "sent":
            stats["skipped"] += 1
            continue
        if delivery is None:
            delivery = DigestDelivery(
                user_id=current_user_id,
                digest_date=digest_date,
                channel="email",
                status="pending",
            )
            session.add(delivery)
        delivery.error = None

        try:
            digest = await build_digest(session, user, digest_date=digest_date)
            if not digest["has_content"]:
                delivery.status = "skipped"
                delivery.error = "no_content"
                stats["skipped"] += 1
                await session.commit()
                continue

            subject, text, html = render_digest_email(digest)
            await send_email(user.email or "", subject, text, html)
            delivery.status = "sent"
            delivery.sent_at = datetime.now(UTC)
            stats["sent"] += 1
        except EmailNotConfigured:
            # Configuration issues are actionable; surface them to the caller.
            raise
        except Exception as exc:  # noqa: BLE001 - one user must not block the batch
            logger.exception("digest email failed user=%s", current_user_id)
            await session.rollback()
            delivery = await session.scalar(
                select(DigestDelivery).where(
                    DigestDelivery.user_id == current_user_id,
                    DigestDelivery.digest_date == digest_date,
                    DigestDelivery.channel == "email",
                )
            )
            if delivery is None:
                delivery = DigestDelivery(
                    user_id=current_user_id,
                    digest_date=digest_date,
                    channel="email",
                )
                session.add(delivery)
            delivery.status = "failed"
            delivery.error = str(exc)[:500]
            stats["failed"] += 1
            await session.commit()
            continue

        await session.commit()

    return stats


__all__ = ["send_daily_digests"]
