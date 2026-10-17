from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

Category = Literal["stock", "industry", "macro"]
Direction = Literal["bullish", "bearish", "neutral"]
Horizon = Literal["intraday", "short", "medium", "long"]


class StockMention(BaseModel):
    code: str | None = None
    name: str
    relevance: float = Field(default=0.8, ge=0.0, le=1.0)
    sentiment: float = Field(default=0.0, ge=-1.0, le=1.0)


class IndustryMention(BaseModel):
    code: str | None = None
    name: str
    relevance: float = Field(default=0.7, ge=0.0, le=1.0)


class MacroMention(BaseModel):
    tag: str
    relevance: float = Field(default=0.7, ge=0.0, le=1.0)


class ReportAnalysisResult(BaseModel):
    primary_category: Category
    categories: list[Category] = Field(min_length=1)
    score: float = Field(ge=-1.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    direction: Direction
    horizon: Horizon = "short"
    summary: str = Field(min_length=1, max_length=500)
    opinion: str = Field(default="", max_length=500)
    key_points: list[str] = Field(default_factory=list, max_length=6)
    keywords: list[str] = Field(default_factory=list, max_length=12)
    stock_mentions: list[StockMention] = Field(default_factory=list)
    industry_mentions: list[IndustryMention] = Field(default_factory=list)
    macro_mentions: list[MacroMention] = Field(default_factory=list)
    rationale: str = Field(default="", max_length=1000)

    @field_validator("categories")
    @classmethod
    def _dedupe_categories(cls, value: list[str]) -> list[str]:
        seen: list[str] = []
        for category in value:
            if category not in seen:
                seen.append(category)
        return seen


class LLMResult(BaseModel):
    analysis: ReportAnalysisResult
    model: str
    fallback: bool = False
    quality_flags: list[str] = Field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0
    raw_output: dict = Field(default_factory=dict)
