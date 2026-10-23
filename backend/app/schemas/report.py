from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel

FeedScope = Literal["following", "discover"]
FeedSort = Literal["time", "smart", "hot", "latest"]
FeedWindow = Literal["24h", "72h", "7d", "30d", "all"]


class AuthorBrief(BaseModel):
    id: int | None = None
    name: str
    weight: float = 1.0
    followed: bool = False
    is_curated: bool = False
    source_layer: str | None = None


class ReportOut(ORMModel):
    id: int
    channel_id: int
    url: str
    title: str
    summary: str | None = None
    opinion: str | None = None
    published_at: datetime
    source_name: str | None = None
    author: AuthorBrief | None = None
    primary_category: str | None = None
    categories: list[str] = Field(default_factory=list)
    stock_codes: list[str] = Field(default_factory=list)
    industry_codes: list[str] = Field(default_factory=list)
    macro_tags: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    score: float | None = None
    display_score: float | None = None
    confidence: float | None = None
    direction: str | None = None
    horizon: str | None = None
    cluster_id: int | None = None
    reprint_count: int = 0
    is_reprint: bool = False


class ReportDetail(ReportOut):
    content: str = ""
    key_points: list[str] = Field(default_factory=list)
    rationale: str | None = None
    stock_mentions: list[dict] = Field(default_factory=list)
    industry_mentions: list[dict] = Field(default_factory=list)
    macro_mentions: list[dict] = Field(default_factory=list)
    analysis_model: str | None = None
    analyzed_at: datetime | None = None


class FeedResponse(BaseModel):
    items: list[ReportOut]
    next_cursor: str | None = None
    has_more: bool = False
    scope: FeedScope = "following"
    sort: str = "smart"
    generated_at: datetime


class InteractionIn(BaseModel):
    saved: bool | None = None
    hidden: bool | None = None
    read: bool | None = None


class InteractionOut(BaseModel):
    report_id: int
    saved: bool = False
    hidden: bool = False
    read_at: datetime | None = None
