from __future__ import annotations

from datetime import datetime
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from app.agents.heuristics import analyze_heuristic
from app.agents.llm import LLMCallError, analyze_with_llm
from app.agents.schemas import LLMResult, ReportAnalysisResult
from app.core.constants import clamp
from app.scoring.text import clean_text, extract_keywords, truncate


class AnalysisState(TypedDict, total=False):
    report_id: int
    title: str
    content: str
    author_name: str | None
    source_name: str | None
    published_at: datetime | None
    candidate_securities: list[dict]
    use_llm: bool
    analysis: ReportAnalysisResult
    meta: dict[str, Any]
    quality_flags: list[str]


async def prepare_node(state: AnalysisState) -> dict[str, Any]:
    content = clean_text(state.get("content") or "")
    title = clean_text(state.get("title") or "")
    flags: list[str] = []
    if len(content) < 120:
        flags.append("low_content")
        content = content or title
    return {"content": content[:12000], "title": title, "quality_flags": flags}


async def analyze_node(state: AnalysisState) -> dict[str, Any]:
    title = state.get("title", "")
    content = state.get("content", "")
    flags = list(state.get("quality_flags") or [])

    result: LLMResult | None = None
    if state.get("use_llm", True):
        try:
            result = await analyze_with_llm(
                title=title,
                content=content,
                author_name=state.get("author_name"),
                source_name=state.get("source_name"),
                published_at=state.get("published_at"),
                candidate_securities=state.get("candidate_securities") or [],
            )
        except LLMCallError:
            flags.append("llm_fallback")

    if result is None:
        analysis = analyze_heuristic(
            title=title,
            content=content,
            candidate_securities=state.get("candidate_securities") or [],
            published_at=state.get("published_at"),
        )
        if "llm_fallback" not in flags:
            flags.append("heuristic_analysis")
        result = LLMResult(
            analysis=analysis,
            model="heuristic",
            fallback=True,
            quality_flags=flags,
        )
    else:
        result.quality_flags = flags

    return {
        "analysis": result.analysis,
        "meta": {
            "model": result.model,
            "fallback": result.fallback,
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "latency_ms": result.latency_ms,
            "raw_output": result.raw_output,
        },
        "quality_flags": flags,
    }


async def normalize_node(state: AnalysisState) -> dict[str, Any]:
    analysis = state["analysis"]
    flags = list(state.get("quality_flags") or [])

    score = round(clamp(float(analysis.score)), 3)
    confidence = round(clamp(float(analysis.confidence), 0.0, 1.0), 3)
    if len(state.get("content") or "") < 120:
        confidence = min(confidence, 0.5)

    if score >= 0.12:
        direction = "bullish"
    elif score <= -0.12:
        direction = "bearish"
    else:
        direction = "neutral"

    categories = list(analysis.categories)
    if analysis.primary_category not in categories:
        categories.insert(0, analysis.primary_category)

    keywords = [word.strip() for word in analysis.keywords if word.strip()]
    if not keywords:
        keywords = extract_keywords(f"{state.get('title', '')}\n{state.get('content', '')}", 8)
    deduped_keywords: list[str] = []
    for word in keywords:
        if word not in deduped_keywords:
            deduped_keywords.append(word)

    summary = analysis.summary.strip() or truncate(state.get("title", ""), 160)
    if not analysis.summary.strip():
        flags.append("summary_from_title")

    seen_stocks: set[str] = set()
    stocks = []
    for mention in analysis.stock_mentions:
        key = mention.code or mention.name
        if key in seen_stocks:
            continue
        seen_stocks.add(key)
        stocks.append(mention)

    normalized = analysis.model_copy(
        update={
            "score": score,
            "confidence": confidence,
            "direction": direction,
            "categories": categories,
            "keywords": deduped_keywords[:12],
            "summary": summary,
            "stock_mentions": stocks,
        }
    )
    return {"analysis": normalized, "quality_flags": flags}


def build_analysis_graph():
    graph = StateGraph(AnalysisState)
    graph.add_node("prepare", prepare_node)
    graph.add_node("analyze", analyze_node)
    graph.add_node("normalize", normalize_node)
    graph.add_edge(START, "prepare")
    graph.add_edge("prepare", "analyze")
    graph.add_edge("analyze", "normalize")
    graph.add_edge("normalize", END)
    return graph.compile()


analysis_graph = build_analysis_graph()


async def run_analysis(
    *,
    report_id: int,
    title: str,
    content: str,
    author_name: str | None = None,
    source_name: str | None = None,
    published_at: datetime | None = None,
    candidate_securities: list[dict] | None = None,
    use_llm: bool = True,
) -> tuple[ReportAnalysisResult, dict[str, Any], list[str]]:
    state: AnalysisState = {
        "report_id": report_id,
        "title": title,
        "content": content,
        "author_name": author_name,
        "source_name": source_name,
        "published_at": published_at,
        "candidate_securities": candidate_securities or [],
        "use_llm": use_llm,
    }
    result = await analysis_graph.ainvoke(state)
    return result["analysis"], result.get("meta") or {}, result.get("quality_flags") or []
