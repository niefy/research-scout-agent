from __future__ import annotations

from sqlalchemy import JSON, Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.base import TimestampMixin


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str | None] = mapped_column(String(255), unique=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(32), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    nickname: Mapped[str] = mapped_column(String(64), nullable=False)
    role: Mapped[str] = mapped_column(String(16), default="user", nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False)
    scoring_config: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    digest_email_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
