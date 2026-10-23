from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import UTCDateTime
from app.models.base import TimestampMixin


class AuthorFollow(Base, TimestampMixin):
    __tablename__ = "author_follows"
    __table_args__ = (UniqueConstraint("user_id", "author_id", name="uq_author_follow"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("authors.id"), nullable=False, index=True)
    weight: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    notify: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class WatchlistItem(Base, TimestampMixin):
    __tablename__ = "watchlist_items"
    __table_args__ = (UniqueConstraint("user_id", "security_id", name="uq_watchlist_item"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    security_id: Mapped[int] = mapped_column(
        ForeignKey("securities.id"), nullable=False, index=True
    )
    note: Mapped[str | None] = mapped_column(String(512))
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class ReportInteraction(Base):
    __tablename__ = "report_interactions"
    __table_args__ = (UniqueConstraint("user_id", "report_id", name="uq_report_interaction"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("reports.id"), nullable=False, index=True)
    read_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    saved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    hidden: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    meta: Mapped[dict] = mapped_column("metadata", JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class ReportSecurityFeedback(Base):
    """Per-user, per-security exclusion of a report from stock scoring."""

    __tablename__ = "report_security_feedback"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "report_id", "security_id", name="uq_report_security_feedback"
        ),
        Index("ix_report_security_feedback_user_security", "user_id", "security_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("reports.id"), nullable=False, index=True)
    security_id: Mapped[int] = mapped_column(
        ForeignKey("securities.id"), nullable=False, index=True
    )
    action: Mapped[str] = mapped_column(String(16), default="irrelevant", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), server_default=func.now(), nullable=False
    )


class DigestDelivery(Base):
    """Idempotency record for a digest sent through one channel."""

    __tablename__ = "digest_deliveries"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "digest_date", "channel", name="uq_digest_delivery"
        ),
        Index("ix_digest_delivery_date", "digest_date", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    digest_date: Mapped[date] = mapped_column(Date, nullable=False)
    channel: Mapped[str] = mapped_column(String(16), default="email", nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    error: Mapped[str | None] = mapped_column(String(512))
    sent_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), server_default=func.now(), nullable=False
    )
