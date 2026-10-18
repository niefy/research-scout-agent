from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
ROOT_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(str(ROOT_DIR / ".env"), str(BACKEND_DIR / ".env")),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # App
    app_name: str = "Research Scout"
    environment: str = "development"
    debug: bool = True
    timezone: str = "Asia/Shanghai"

    # Infrastructure
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/research_scout"
    redis_url: str = "redis://localhost:6379/0"
    sql_echo: bool = False

    # Auth
    jwt_secret: str = "please-change-this-in-production"
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 7

    cors_origins: str = "http://localhost:5173,http://localhost:8080"

    # Bootstrap
    auto_create_tables: bool = True
    seed_on_startup: bool = True
    seed_demo_data: bool = False
    admin_email: str | None = None
    admin_password: str | None = None

    # LLM (OpenAI-compatible)
    llm_protocol: str = "openai"
    llm_base_url: str = "https://api.deepseek.com/v1"
    llm_api_key: str = ""
    llm_model_utility: str = "deepseek-v4-flash"
    llm_model_analyze: str = "deepseek-v4-flash"
    llm_model_aggregate: str = "deepseek-v4-flash"
    llm_daily_budget: float = 0.0
    llm_mock: bool = True

    # Crawl
    crawl_daily_hour: int = 6
    crawl_daily_minute: int = 30
    crawl_request_timeout: int = 15
    crawl_max_items_per_channel: int = 50

    # Startup freshness check: crawl immediately when the last successful
    # crawl is older than this threshold; skip otherwise.
    startup_refresh_enabled: bool = True
    startup_refresh_stale_minutes: int = 60

    @field_validator("database_url")
    @classmethod
    def _normalize_database_url(cls, value: str) -> str:
        value = value.strip()
        if value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+asyncpg://", 1)
        if value.startswith("sqlite:///") and "+aiosqlite" not in value:
            return value.replace("sqlite:///", "sqlite+aiosqlite:///", 1)
        return value

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def llm_enabled(self) -> bool:
        return bool(self.llm_api_key) and not self.llm_mock


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
