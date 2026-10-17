from __future__ import annotations

import json
import re
import time
from datetime import datetime
from typing import Any

from pydantic import ValidationError

from app.agents.prompts import SYSTEM_PROMPT, build_user_prompt
from app.agents.schemas import LLMResult, ReportAnalysisResult
from app.core.config import settings

_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


class LLMCallError(RuntimeError):
    pass


def _message_text(message: Any) -> str:
    content = getattr(message, "content", message)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                text = block.get("text") or block.get("content")
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts)
    return str(content)


def extract_json_object(text: str) -> dict:
    cleaned = _FENCE_RE.sub("", text.strip())
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start < 0 or end <= start:
        raise LLMCallError("LLM response does not contain a JSON object")
    snippet = cleaned[start : end + 1]
    try:
        value = json.loads(snippet)
    except json.JSONDecodeError as exc:
        raise LLMCallError(f"invalid JSON from LLM: {exc}") from exc
    if not isinstance(value, dict):
        raise LLMCallError("LLM JSON root must be an object")
    return value


def _usage_tokens(message: Any) -> tuple[int, int]:
    usage = getattr(message, "usage_metadata", None) or {}
    if isinstance(usage, dict):
        return int(usage.get("input_tokens") or 0), int(usage.get("output_tokens") or 0)
    return 0, 0


async def analyze_with_llm(
    *,
    title: str,
    content: str,
    author_name: str | None,
    source_name: str | None,
    published_at: datetime | None,
    candidate_securities: list[dict] | None = None,
    model: str | None = None,
) -> LLMResult:
    if not settings.llm_enabled:
        raise LLMCallError("LLM is disabled (set LLM_API_KEY and LLM_MOCK=false)")

    from langchain_openai import ChatOpenAI

    model_name = model or settings.llm_model_analyze
    llm = ChatOpenAI(
        model=model_name,
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        temperature=0.1,
        timeout=90,
        max_retries=1,
    )

    started = time.perf_counter()
    try:
        message = await llm.ainvoke(
            [
                ("system", SYSTEM_PROMPT),
                (
                    "user",
                    build_user_prompt(
                        title=title,
                        content=content,
                        author_name=author_name,
                        source_name=source_name,
                        published_at=published_at,
                        candidate_securities=candidate_securities,
                    ),
                ),
            ]
        )
    except Exception as exc:
        raise LLMCallError(f"LLM request failed: {exc}") from exc
    latency_ms = int((time.perf_counter() - started) * 1000)

    text = _message_text(message)
    try:
        payload = extract_json_object(text)
        analysis = ReportAnalysisResult.model_validate(payload)
    except (LLMCallError, ValidationError) as exc:
        raise LLMCallError(f"LLM output validation failed: {exc}") from exc

    input_tokens, output_tokens = _usage_tokens(message)
    return LLMResult(
        analysis=analysis,
        model=model_name,
        fallback=False,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        latency_ms=latency_ms,
        raw_output=payload,
    )
