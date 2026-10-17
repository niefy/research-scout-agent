from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Float,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import UTCDateTime
from app.models.base import TimestampMixin


class Industry(Base, TimestampMixin):
    __tablename__ = "industries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    parent_code: Mapped[str | None] = mapped_column(String(32), index=True)
    level: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    aliases: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Security(Base, TimestampMixin):
    __tablename__ = "securities"
    __table_args__ = (UniqueConstraint("code", name="uq_security_code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    symbol: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    exchange: Mapped[str] = mapped_column(String(16), default="SH", nullable=False)
    industry_code: Mapped[str | None] = mapped_column(String(32), index=True)
    aliases: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    meta: Mapped[dict] = mapped_column("metadata", JSON, default=dict, nullable=False)


class StockScoreSnapshot(Base):
    __tablename__ = "stock_score_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    security_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    user_id: Mapped[int | None] = mapped_column(Integer, index=True)
    scope: Mapped[str] = mapped_column(String(16), default="all", nullable=False)
    window: Mapped[str] = mapped_column(String(16), default="30d", nullable=False)
    report_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    raw_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    final_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    qualitative_score: Mapped[float | None] = mapped_column(Float)
    adjustment: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    n_eff: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    conclusion: Mapped[str] = mapped_column(String(512), default="", nullable=False)
    breakdown: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    computed_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), server_default=func.now(), nullable=False
    )
