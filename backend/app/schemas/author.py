from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class AuthorOut(ORMModel):
    id: int
    canonical_name: str
    author_type: str
    default_weight: float
    status: str
    meta: dict = Field(default_factory=dict)
    created_at: datetime


class AuthorCreate(BaseModel):
    canonical_name: str = Field(min_length=1, max_length=128)
    author_type: str = Field(default="analyst", max_length=16)
    default_weight: float = Field(default=1.0, ge=0.1, le=5.0)
    aliases: list[str] = Field(default_factory=list)


class AuthorUpdate(BaseModel):
    canonical_name: str | None = Field(default=None, min_length=1, max_length=128)
    author_type: str | None = Field(default=None, max_length=16)
    default_weight: float | None = Field(default=None, ge=0.1, le=5.0)
    status: str | None = Field(default=None, max_length=16)


class AuthorFollowIn(BaseModel):
    weight: float = Field(default=1.0, ge=0.1, le=5.0)
    notify: bool = False


class AuthorFollowOut(BaseModel):
    author: AuthorOut
    weight: float
    notify: bool
    followed_at: datetime


class AuthorIdentityOut(ORMModel):
    id: int
    channel_id: int
    external_id: str
    display_name: str | None = None
    profile_url: str | None = None


class AuthorDetail(AuthorOut):
    aliases: list[str] = Field(default_factory=list)
    identities: list[AuthorIdentityOut] = Field(default_factory=list)
    follower_count: int = 0
    report_count: int = 0
