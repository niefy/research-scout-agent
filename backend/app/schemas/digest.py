from __future__ import annotations

from datetime import date as DateType
from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.author import RecommendedAuthorOut
from app.schemas.report import ReportOut
from app.schemas.stock import EvidenceOut, ScoreScope, SecurityOut


class DigestUserOut(BaseModel):
    id: int
    nickname: str
    email: str | None = None


class DigestWatchlistChange(BaseModel):
    security: SecurityOut
    display_score: float | None = None
    display_label: str = "综合得分"
    evidence: EvidenceOut = Field(default_factory=EvidenceOut)
    relation_counts: dict[str, int] = Field(default_factory=dict)
    report_count: int = 0
    previous_total_points: float | None = None
    score_delta: float | None = None
    delta_since: datetime | None = None
    evidence_gaps: list[str] = Field(default_factory=list)


class DigestEvidenceGap(BaseModel):
    security: SecurityOut
    gaps: list[str] = Field(default_factory=list)
    evidence_level: str = "none"


class DigestResponse(BaseModel):
    date: DateType
    generated_at: datetime
    user: DigestUserOut
    scope: ScoreScope = "hybrid"
    window: str = "30d"
    followed_updates: list[ReportOut] = Field(default_factory=list)
    watchlist_changes: list[DigestWatchlistChange] = Field(default_factory=list)
    evidence_gaps: list[DigestEvidenceGap] = Field(default_factory=list)
    recommended_authors: list[RecommendedAuthorOut] = Field(default_factory=list)
    has_content: bool = False


class DigestSendIn(BaseModel):
    date: DateType | None = None
    user_id: int | None = None


class DigestSendOut(BaseModel):
    users: int = 0
    sent: int = 0
    skipped: int = 0
    failed: int = 0
    skipped_reason: str | None = None


__all__ = [
    "DigestEvidenceGap",
    "DigestResponse",
    "DigestSendIn",
    "DigestSendOut",
    "DigestUserOut",
    "DigestWatchlistChange",
]
