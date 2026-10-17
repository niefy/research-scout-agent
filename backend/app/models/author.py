from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
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


class Author(Base, TimestampMixin):
    __tablename__ = "authors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    canonical_name: Mapped[str] = mapped_column(String(128), nullable=False)
    normalized_name: Mapped[str] = mapped_column(
        String(128), unique=True, index=True, nullable=False
    )
    author_type: Mapped[str] = mapped_column(String(16), default="unknown", nullable=False)
    default_weight: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False)
    merged_into_id: Mapped[int | None] = mapped_column(ForeignKey("authors.id"))
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    meta: Mapped[dict] = mapped_column("metadata", JSON, default=dict, nullable=False)


class AuthorAlias(Base):
    __tablename__ = "author_aliases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("authors.id"), nullable=False, index=True)
    alias: Mapped[str] = mapped_column(String(128), nullable=False)
    normalized_alias: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    channel_id: Mapped[int | None] = mapped_column(ForeignKey("channels.id"))
    confidence: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    source: Mapped[str] = mapped_column(String(16), default="manual", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), server_default=func.now(), nullable=False
    )


class AuthorIdentity(Base):
    __tablename__ = "author_identities"
    __table_args__ = (
        UniqueConstraint("channel_id", "external_id", name="uq_author_identity_channel_external"),
        Index("ix_author_identity_author", "author_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("authors.id"), nullable=False)
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id"), nullable=False)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(128))
    profile_url: Mapped[str | None] = mapped_column(String(1024))
    meta: Mapped[dict] = mapped_column("metadata", JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), server_default=func.now(), nullable=False
    )
