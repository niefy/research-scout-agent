from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel
from app.schemas.report import ReportOut

ScoreScope = Literal["personal", "hybrid", "all"]
Relation = Literal["stock", "industry", "macro"]
RelationReason = Literal[
    "direct_mention", "stock_code_fallback", "industry_code", "macro"
]
EvidenceLevel = Literal["direct", "industry", "macro", "none"]


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


class EvidenceOut(BaseModel):
    level: EvidenceLevel = "none"
    label: str = "证据不足"
    stock_count: int = 0
    industry_count: int = 0
    macro_count: int = 0
    distinct_authors: int = 0
    coverage: dict[str, bool] = Field(default_factory=dict)
    is_macro_only: bool = False
    is_insufficient: bool = True


class ScoreBreakdownItem(BaseModel):
    report_id: int
    title: str
    relation: Relation
    relation_reason: RelationReason
    score: float
    confidence: float
    author_weight: float
    relation_weight: float
    recency_factor: float
    relevance: float
    effective_weight: float
    published_at: datetime
    author_name: str | None = None
    source_name: str | None = None


class RelationScoreOut(BaseModel):
    relation: Relation
    budget_share: float
    budget_points: float
    article_count: int
    weighted_signal: float
    points: float
    weight_sum: float
    confidence: float


class StockScoreOut(BaseModel):
    security: SecurityOut
    scope: ScoreScope = "hybrid"
    window: str = "30d"
    report_count: int = 0
    raw_score: float = 0.0
    final_score: float = 0.0
    total_points: float = 0.0
    display_score: float | None = None
    display_label: str = "综合得分"
    n_eff: float = 0.0
    confidence: float = 0.0
    conclusion: str = ""
    evidence: EvidenceOut = Field(default_factory=EvidenceOut)
    relation_scores: list[RelationScoreOut] = Field(default_factory=list)
    relation_counts: dict[str, int] = Field(default_factory=dict)
    relation_weights: dict[str, float] = Field(default_factory=dict)
    half_life_days: dict[str, float] = Field(default_factory=dict)
    max_age_days: float = 90.0
    breakdown: list[ScoreBreakdownItem] = Field(default_factory=list)
    previous_total_points: float | None = None
    score_delta: float | None = None
    delta_since: datetime | None = None
    computed_at: datetime | None = None


class RelatedReportOut(ReportOut):
    relation: Relation | None = None
    relation_reason: RelationReason | None = None


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
    related_reports: list[RelatedReportOut] = Field(default_factory=list)


class StockHistoryPointOut(BaseModel):
    computed_at: datetime
    total_points: float
    display_score: float | None = None
    evidence_level: EvidenceLevel = "none"
    report_count: int = 0
    relation_counts: dict[str, int] = Field(default_factory=dict)


class StockHistoryOut(BaseModel):
    security: SecurityOut
    scope: ScoreScope
    window: str
    points: list[StockHistoryPointOut] = Field(default_factory=list)
    deltas: dict[str, float | None] = Field(default_factory=dict)


class FeedbackIn(BaseModel):
    report_id: int
    action: Literal["irrelevant"] = "irrelevant"


class FeedbackOut(BaseModel):
    message: str
    security_code: str
    report_id: int
    excluded: bool
