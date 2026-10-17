from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel
from app.schemas.report import ReportOut


class SecurityOut(ORMModel):
    id: int
    code: str
    symbol: str
    name: str
    exchange: str
    industry_code: str | None = None
    aliases: list[str] = Field(default_factory=list)


class WatchlistAdd(BaseModel):
    security_id: int | None = None
    code: str | None = None
    note: str | None = Field(default=None, max_length=512)


class WatchlistUpdate(BaseModel):
    note: str | None = Field(default=None, max_length=512)
    sort_order: int | None = None


class ScoreBreakdownItem(BaseModel):
    report_id: int
    title: str
    category: str
    score: float
    confidence: float
    author_weight: float
    category_weight: float
    recency_factor: float
    relevance: float
    effective_weight: float
    published_at: datetime


class CategoryScoreOut(BaseModel):
    category: str
    budget_share: float
    budget_points: float
    article_count: int
    weighted_signal: float
    points: float
    weight_sum: float
    confidence: float


class StockScoreOut(BaseModel):
    security: SecurityOut
    scope: Literal["all", "followed"] = "all"
    window: str = "30d"
    report_count: int = 0
    raw_score: float = 0.0
    final_score: float = 0.0
    total_points: float = 0.0
    display_score: float | None = None
    n_eff: float = 0.0
    confidence: float = 0.0
    conclusion: str = ""
    category_scores: list[CategoryScoreOut] = Field(default_factory=list)
    category_weights: dict[str, float] = Field(default_factory=dict)
    half_life_days: dict[str, float] = Field(default_factory=dict)
    max_age_days: float = 90.0
    breakdown: list[ScoreBreakdownItem] = Field(default_factory=list)
    category_counts: dict[str, int] = Field(default_factory=dict)
    computed_at: datetime | None = None


class WatchlistItemOut(BaseModel):
    id: int
    security: SecurityOut
    note: str | None = None
    sort_order: int = 0
    score: StockScoreOut | None = None
    added_at: datetime


class StockDetailOut(BaseModel):
    security: SecurityOut
    score: StockScoreOut
    related_reports: list[ReportOut] = Field(default_factory=list)
