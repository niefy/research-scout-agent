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


class AuthorCurationUpdate(BaseModel):
    is_curated: bool | None = None
    curated_rank: int | None = Field(default=None, ge=0)
    crawl_enabled: bool | None = None
    quality_score: float | None = Field(default=None, ge=0.0, le=1.0)
    sector_tags: list[str] | None = None


class AuthorIdentityIn(BaseModel):
    channel_code: str = Field(default="xueqiu", max_length=64)
    external_id: str = Field(min_length=1, max_length=255)
    display_name: str | None = Field(default=None, max_length=128)
    profile_url: str | None = Field(default=None, max_length=1024)


class AuthorIdentityBindOut(BaseModel):
    author_id: int
    channel_id: int
    external_id: str
    display_name: str | None = None
    profile_url: str | None = None


class AuthorCrawlRequest(BaseModel):
    author_ids: list[int] | None = None
    force: bool = False
    limit: int | None = Field(default=None, ge=1, le=100)
    analyze: bool = True


class AuthorCrawlResponse(BaseModel):
    authors: int = 0
    candidate_authors: int = 0
    targets: int = 0
    skipped_fresh: int = 0
    no_identity: list[int] = Field(default_factory=list)
    fetched: int = 0
    created: int = 0
    duplicated: int = 0
    failed: int = 0
    conflicts: int = 0
    analysis: dict | None = None
    runs: list[dict] = Field(default_factory=list)


class SourceHealthChannelOut(BaseModel):
    channel_code: str
    name: str
    adapter_key: str
    enabled: bool
    credential_configured: bool | None = None
    last_run_at: datetime | None = None
    last_status: str | None = None
    last_error: str | None = None
    last_fetched: int = 0
    last_created: int = 0


class SourceHealthAuthorOut(BaseModel):
    author_id: int
    canonical_name: str
    is_curated: bool = False
    crawl_enabled: bool = True
    crawl_status: str = "idle"
    last_crawled_at: datetime | None = None
    crawl_error: str | None = None
    identity_count: int = 0


class SourceHealthOut(BaseModel):
    generated_at: datetime
    channels: list[SourceHealthChannelOut] = Field(default_factory=list)
    authors: list[SourceHealthAuthorOut] = Field(default_factory=list)


class IngestRunOut(ORMModel):
    id: int
    run_type: str
    channel_id: int | None = None
    author_id: int | None = None
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
