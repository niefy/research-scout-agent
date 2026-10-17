from __future__ import annotations

import math
from collections import deque
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TypeVar

from app.scoring.stock import as_utc, recency_factor

T = TypeVar("T")

HOT_HALF_LIFE_HOURS = 48.0


def hot_signal(confidence: float | None, score: float | None) -> float:
    confidence = max(0.0, min(1.0, float(confidence or 0.0)))
    score = max(-1.0, min(1.0, float(score or 0.0)))
    return 0.5 + 0.5 * confidence * abs(score)


def hot_score(
    *,
    default_weight: float,
    published_at: datetime,
    confidence: float | None,
    score: float | None,
    reprint_count: int = 0,
    engagement: int = 0,
    now: datetime | None = None,
) -> float:
    now = now or datetime.now(UTC)
    age_hours = max(0.0, (as_utc(now) - as_utc(published_at)).total_seconds() / 3600.0)
    freshness = 0.5 ** (age_hours / HOT_HALF_LIFE_HOURS)
    weight = max(0.0, float(default_weight or 0.0)) ** 0.5
    signal = hot_signal(confidence, score)
    reprint_boost = 1.0 + 0.15 * math.log1p(max(0, reprint_count))
    engagement_boost = 1.0 + 0.10 * math.log1p(max(0, engagement))
    return weight * freshness * signal * reprint_boost * engagement_boost


def smart_score(
    *,
    published_at: datetime,
    confidence: float | None,
    score: float | None,
    category_weight: float,
    author_weight: float,
    priority: bool = False,
    now: datetime | None = None,
) -> float:
    """Personal feed sort: relevance first, freshness second.

    Unlike the hot feed this uses a longer half-life and rewards directional
    conviction, so a strong call from a followed author stays visible for days.
    """
    now = now or datetime.now(UTC)
    freshness = recency_factor(published_at, now, half_life_days=3.0)
    conviction = hot_signal(confidence, score)
    personal = math.sqrt(max(0.0, author_weight)) * max(0.0, category_weight)
    boost = 1.25 if priority else 1.0
    return freshness * conviction * personal * boost


@dataclass
class DiversityLimits:
    max_per_author: int = 2
    max_per_category: int = 6
    window: int = 20


def diversify(
    items: Iterable[T],
    *,
    key_author: Callable[[T], object],
    key_cluster: Callable[[T], object],
    key_category: Callable[[T], object],
    limit: int,
    limits: DiversityLimits | None = None,
) -> list[T]:
    """Rerank an already sorted pool, applying cluster/author/category caps.

    Cluster de-duplication is absolute. Author and category caps are applied
    over a sliding window of ``limits.window`` selected items. If the strict
    pass cannot fill ``limit``, a second pass relaxes the author/category caps
    but still never repeats a cluster.
    """
    limits = limits or DiversityLimits()
    selected: list[T] = []
    seen_clusters: set[object] = set()
    window: deque[T] = deque()

    def window_count(key: Callable[[T], object], value: object) -> int:
        return sum(1 for entry in window if key(entry) == value)

    for item in items:
        if len(selected) >= limit:
            break
        cluster = key_cluster(item)
        if cluster is not None and cluster in seen_clusters:
            continue
        author = key_author(item)
        category = key_category(item)
        if author is not None and window_count(key_author, author) >= limits.max_per_author:
            continue
        if (
            category is not None
            and window_count(key_category, category) >= limits.max_per_category
        ):
            continue

        selected.append(item)
        if cluster is not None:
            seen_clusters.add(cluster)
        window.append(item)
        if len(window) > limits.window:
            window.popleft()

    if len(selected) < limit:
        for item in items:
            if len(selected) >= limit:
                break
            if any(item is existing for existing in selected):
                continue
            cluster = key_cluster(item)
            if cluster is not None and cluster in seen_clusters:
                continue
            selected.append(item)
            if cluster is not None:
                seen_clusters.add(cluster)

    return selected
