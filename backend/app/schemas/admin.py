from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class ChannelOut(ORMModel):
    id: int
    code: str
    name: str
    adapter_key: str
    enabled: bool
    config: dict = Field(default_factory=dict)
    crawl_interval_seconds: int
    last_cursor: dict = Field(default_factory=dict)
    updated_at: datetime


class ChannelUpdate(BaseModel):
    enabled: bool | None = None
    config: dict | None = None
    crawl_interval_seconds: int | None = Field(default=None, ge=60)


class CrawlRequest(BaseModel):
    channel_codes: list[str] | None = None
    analyze: bool = True
    limit: int | None = Field(default=None, ge=1, le=200)


class CrawlChannelResult(BaseModel):
    channel_code: str
    fetched: int = 0
    created: int = 0
    duplicated: int = 0
    failed: int = 0
    error: str | None = None


class CrawlResponse(BaseModel):
    results: list[CrawlChannelResult]
    analyzed: int = 0
    analysis_failed: int = 0


class AnalyzeRequest(BaseModel):
    limit: int = Field(default=50, ge=1, le=500)
    force: bool = False
    report_ids: list[int] | None = None


class AnalyzeResponse(BaseModel):
    candidates: int
    analyzed: int
    failed: int


class AdapterOut(BaseModel):
    key: str
    display_name: str


class IngestRunOut(ORMModel):
    id: int
    run_type: str
    channel_id: int | None = None
    status: str
    started_at: datetime
    finished_at: datetime | None = None
    stats: dict = Field(default_factory=dict)
    error: str | None = None


class SystemStatsOut(BaseModel):
    reports_total: int
    reports_analyzed: int
    authors_total: int
    users_total: int
    channels_enabled: int
    llm_calls_today: int
    llm_tokens_today: int
    llm_fallbacks_today: int
