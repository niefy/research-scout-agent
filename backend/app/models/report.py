from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import UTCDateTime
from app.models.base import TimestampMixin


class ReportCluster(Base):
    __tablename__ = "report_clusters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    canonical_report_id: Mapped[int | None] = mapped_column(Integer)
    simhash: Mapped[str | None] = mapped_column(String(16), index=True)
    size: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), server_default=func.now(), nullable=False
    )


class Report(Base, TimestampMixin):
    __tablename__ = "reports"
    __table_args__ = (
        UniqueConstraint("channel_id", "external_id", name="uq_report_channel_external"),
        Index("ix_report_published", "published_at"),
        Index("ix_report_author_published", "author_id", "published_at"),
        Index("ix_report_primary_category", "primary_category", "published_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id"), nullable=False, index=True)
    external_id: Mapped[str | None] = mapped_column(String(255))
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    content: Mapped[str] = mapped_column(Text, default="", nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    opinion: Mapped[str | None] = mapped_column(Text)

    author_id: Mapped[int | None] = mapped_column(ForeignKey("authors.id"), index=True)
    raw_author_name: Mapped[str | None] = mapped_column(String(128))
    source_name: Mapped[str | None] = mapped_column(String(128))

    published_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), server_default=func.now(), nullable=False
    )
    language: Mapped[str] = mapped_column(String(8), default="zh", nullable=False)

    content_hash: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    simhash: Mapped[str | None] = mapped_column(String(16), index=True)
    cluster_id: Mapped[int | None] = mapped_column(ForeignKey("report_clusters.id"), index=True)
    is_reprint: Mapped[bool] = mapped_column(default=False, nullable=False)
    reprint_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    primary_category: Mapped[str | None] = mapped_column(String(16), index=True)
    categories: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    stock_codes: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    industry_codes: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    macro_tags: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    keywords: Mapped[list] = mapped_column(JSON, default=list, nullable=False)

    score: Mapped[float | None] = mapped_column(Float)
    confidence: Mapped[float | None] = mapped_column(Float)
    direction: Mapped[str | None] = mapped_column(String(16))
    horizon: Mapped[str | None] = mapped_column(String(16))

    analysis_status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    current_analysis_id: Mapped[int | None] = mapped_column(Integer)
    engagement: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    meta: Mapped[dict] = mapped_column("metadata", JSON, default=dict, nullable=False)


class ReportAnalysis(Base):
    __tablename__ = "report_analyses"
    __table_args__ = (Index("ix_report_analysis_report", "report_id", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("reports.id"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(32), default="v1", nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)

    primary_category: Mapped[str] = mapped_column(String(16), nullable=False)
    categories: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    horizon: Mapped[str] = mapped_column(String(16), default="short", nullable=False)
    summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    opinion: Mapped[str] = mapped_column(Text, default="", nullable=False)
    key_points: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    keywords: Mapped[list] = mapped_column(JSON, default=list, nullable=False)

    stock_mentions: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    industry_mentions: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    macro_mentions: Mapped[list] = mapped_column(JSON, default=list, nullable=False)

    rationale: Mapped[str] = mapped_column(Text, default="", nullable=False)
    quality_flags: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    raw_output: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    input_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), server_default=func.now(), nullable=False
    )
