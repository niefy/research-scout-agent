from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.llm import LLMCallError, extract_json_object
from app.core.config import settings
from app.core.constants import clamp
from app.models.security import StockScoreSnapshot
from app.services.stocks import StockScore

logger = logging.getLogger(__name__)

CACHE_TTL = timedelta(hours=6)
TOP_REPORTS = 8

SYSTEM_PROMPT = """你是一名 A 股研究组合经理。
你会收到某只股票近期相关报告的结构化摘要、打分和证据等级。
请给出：
1. conclusion：不超过 150 字的中文结论，说明多空逻辑、关键分歧和需要跟踪的验证点。
2. qualitative_score：-1 到 1，表示综合考虑基本面、催化剂、预期差和风险后的定性判断。
重要约束：
- 如果证据等级是 macro，只能写“宏观参考”，明确说明缺少个股和行业证据，不得伪装成个股综合结论。
- 如果证据等级是 industry，说明这是行业参考，并指出缺少个股直接证据。
- 如果证据等级是 none，只说明证据不足，不要编造结论。
只输出 JSON：{"conclusion": "...", "qualitative_score": 0.0}"""


async def get_cached_conclusion(
    session: AsyncSession,
    *,
    user_id: int,
    security_id: int,
    scope: str,
    window: str,
    report_ids: list[int],
) -> tuple[str, float] | None:
    cutoff = datetime.now(UTC) - CACHE_TTL
    snapshot = await session.scalar(
        select(StockScoreSnapshot)
        .where(
            StockScoreSnapshot.user_id == user_id,
            StockScoreSnapshot.security_id == security_id,
            StockScoreSnapshot.scope == scope,
            StockScoreSnapshot.window == window,
            StockScoreSnapshot.computed_at >= cutoff,
            StockScoreSnapshot.qualitative_score.is_not(None),
        )
        .order_by(StockScoreSnapshot.computed_at.desc())
        .limit(1)
    )
    if snapshot is None:
        return None
    cached_ids = (snapshot.breakdown or {}).get("report_ids") or []
    if sorted(cached_ids) != sorted(report_ids):
        return None
    if not snapshot.conclusion or snapshot.qualitative_score is None:
        return None
    return snapshot.conclusion, float(snapshot.qualitative_score)


async def generate_conclusion(
    score: StockScore,
) -> tuple[str, float] | None:
    if not settings.llm_enabled or not score.entries:
        return None

    lines: list[str] = []
    ranked = sorted(
        score.result.breakdown,
        key=lambda item: item.effective_weight * abs(item.score),
        reverse=True,
    )[:TOP_REPORTS]
    entries_by_id = {entry.report.id: entry for entry in score.entries}
    for item in ranked:
        entry = entries_by_id.get(item.report_id)
        summary = (entry.report.summary or entry.report.title) if entry else item.title
        lines.append(
            f"- [{item.relation}] 标题：{item.title}；报告分 {item.score:+.2f}；"
            f"摘要：{summary[:160]}"
        )

    user_prompt = (
        f"股票：{score.security.name}（{score.security.code}）\n"
        f"窗口：{score.window}\n"
        f"纳入报告数：{score.result.report_count}\n"
        f"关系分布：{json.dumps(score.result.relation_counts, ensure_ascii=False)}\n"
        f"证据等级：{score.evidence.level}（{score.evidence.label}）\n"
        f"证据计数：个股{score.evidence.stock_count}、"
        f"行业{score.evidence.industry_count}、宏观{score.evidence.macro_count}\n"
        f"评分：{score.result.total_points:.1f}/100\n"
        f"关系得分："
        + "、".join(
            f"{item.relation} {item.points:.1f}/{item.budget_points:.1f}"
            for item in score.result.relation_scores
        )
        + "\n"
        f"有效样本 n_eff：{score.result.n_eff:.1f}\n"
        f"相关报告：\n" + "\n".join(lines) + "\n\n请输出 JSON。"
    )

    try:
        from langchain_openai import ChatOpenAI

        llm = ChatOpenAI(
            model=settings.llm_model_aggregate,
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            temperature=0.2,
            timeout=60,
            max_retries=1,
        )
        message = await llm.ainvoke(
            [("system", SYSTEM_PROMPT), ("user", user_prompt)]
        )
        text = message.content if isinstance(message.content, str) else str(message.content)
        payload = extract_json_object(text)
        conclusion = str(payload.get("conclusion") or "").strip()
        qualitative = clamp(float(payload.get("qualitative_score") or 0.0))
        if not conclusion:
            return None
        return conclusion[:400], qualitative
    except (LLMCallError, ValueError, TypeError) as exc:
        logger.warning("LLM conclusion failed for %s: %s", score.security.code, exc)
    except Exception as exc:  # noqa: BLE001 - conclusion is optional
        logger.warning("LLM conclusion error for %s: %s", score.security.code, exc)
    return None


async def enrich_detail_with_conclusion(
    session: AsyncSession,
    *,
    user_id: int,
    score: StockScore,
) -> StockScore:
    """Attach a cached or freshly generated LLM narrative to a stock score.

    The numeric score is fully deterministic (relation budgets + time-decayed
    article weights). The LLM only writes the qualitative conclusion; it never
    changes the points or the chart. Snapshot persistence is handled by the
    caller so it also works when no LLM is configured.
    """
    report_ids = sorted(item.report_id for item in score.result.breakdown)
    if not report_ids:
        return score

    cached = await get_cached_conclusion(
        session,
        user_id=user_id,
        security_id=score.security.id,
        scope=score.scope,
        window=score.window,
        report_ids=report_ids,
    )
    if cached is None:
        generated = await generate_conclusion(score)
        if generated is None:
            return score
        conclusion, qualitative = generated
        score.conclusion = conclusion
        score.qualitative_score = qualitative
        return score

    conclusion, qualitative = cached
    score.conclusion = conclusion
    score.qualitative_score = qualitative
    return score
