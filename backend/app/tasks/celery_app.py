from __future__ import annotations

from datetime import timedelta

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
        "author-crawl": {
            "task": "app.tasks.jobs.crawl_authors_and_analyze",
            "schedule": timedelta(
                minutes=max(1, settings.author_crawl_interval_minutes)
            ),
        },
        "daily-score-snapshots": {
            "task": "app.tasks.jobs.snapshot_scores",
            "schedule": crontab(
                hour=settings.crawl_daily_hour,
                minute=50,
            ),
        },
        "daily-digest-email": {
            "task": "app.tasks.jobs.send_daily_digests",
            "schedule": crontab(
                hour=settings.digest_email_hour,
                minute=settings.digest_email_minute,
            ),
        },
    },
)


__all__ = ["celery_app"]
