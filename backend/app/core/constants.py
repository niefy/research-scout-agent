from __future__ import annotations

from enum import StrEnum


class Category(StrEnum):
    STOCK = "stock"
    INDUSTRY = "industry"
    MACRO = "macro"


ALL_CATEGORIES: tuple[str, ...] = (Category.STOCK, Category.INDUSTRY, Category.MACRO)

DEFAULT_CATEGORY_WEIGHTS: dict[str, float] = {
    Category.STOCK: 1.0,
    Category.INDUSTRY: 0.5,
    Category.MACRO: 0.25,
}

# Budget shares for the stock composite score (40 / 40 / 20 out of 100).
CATEGORY_BUDGET_WEIGHTS: dict[str, float] = {
    Category.STOCK: 0.4,
    Category.INDUSTRY: 0.4,
    Category.MACRO: 0.2,
}

DEFAULT_HALF_LIFE_DAYS: dict[str, float] = {
    Category.STOCK: 7.0,
    Category.INDUSTRY: 14.0,
    Category.MACRO: 30.0,
}

# Reports older than this are never considered by the stock aggregator.
MAX_REPORT_AGE_DAYS = 90.0

SCORE_MIN = -1.0
SCORE_MAX = 1.0
CONFIDENCE_MIN = 0.0
CONFIDENCE_MAX = 1.0

# Shrinkage constant for the effective-number-of-reports correction.
AGGREGATION_SHRINK_K = 3.0
# Hard cap on the LLM qualitative adjustment of an aggregate score.
QUALITATIVE_ADJUSTMENT_LIMIT = 0.10

DISPLAY_SCORE_BASE = 50.0
DISPLAY_SCORE_SCALE = 50.0


def display_score(score: float | None) -> float | None:
    if score is None:
        return None
    return round(DISPLAY_SCORE_BASE + DISPLAY_SCORE_SCALE * score, 1)


def clamp(value: float, low: float = SCORE_MIN, high: float = SCORE_MAX) -> float:
    return max(low, min(high, value))
