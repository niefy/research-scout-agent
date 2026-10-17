from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

celery_app = Celery(
    "research_scout",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.tasks.jobs"],
)

celery_app.conf.update(
    timezone=settings.timezone,
    enable_utc=True,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    worker_max_tasks_per_child=50,
    beat_schedule={
        "daily-crawl-and-analyze": {
            "task": "app.tasks.jobs.crawl_and_analyze",
            "schedule": crontab(
                hour=settings.crawl_daily_hour,
                minute=settings.crawl_daily_minute,
            ),
        },
    },
)


__all__ = ["celery_app"]
