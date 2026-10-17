from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from app.agents.schemas import (
    IndustryMention,
    MacroMention,
    ReportAnalysisResult,
    StockMention,
)
from app.core.constants import clamp
from app.scoring.text import extract_keywords, normalize_text, truncate

_CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "stock": (
        "营收",
        "净利润",
        "归母",
        "业绩",
        "订单",
        "评级",
        "目标价",
        "调研",
        "股东",
        "回购",
        "增持",
        "减持",
        "涨停",
        "跌停",
        "股价",
        "市值",
        "估值",
        "毛利率",
        "分红",
        "中标",
        "签约",
        "单季",
        "财报",
        "三季报",
        "半年报",
    ),
    "industry": (
        "行业",
        "产业链",
        "产能",
        "扩产",
        "渗透率",
        "需求",
        "供给",
        "价格战",
        "库存",
        "出货量",
        "装机",
        "开工率",
        "景气度",
        "国产替代",
        "市场份额",
        "竞争格局",
        "上游",
        "下游",
        "材料",
        "设备",
    ),
    "macro": (
        "央行",
        "mlf",
        "lpr",
        "降准",
        "降息",
        "利率",
        "流动性",
        "社融",
        "cpi",
        "ppi",
        "gdp",
        "财政",
        "政策",
        "美联储",
        "汇率",
        "国债",
        "关税",
        "出口",
        "pmi",
        "经济",
        "通胀",
        "信贷",
        "货币",
    ),
}

_POSITIVE_WORDS = (
    "增长",
    "提升",
    "改善",
    "超预期",
    "买入",
    "增持",
    "利好",
    "强劲",
    "回暖",
    "净投放",
    "上调",
    "突破",
    "创新高",
    "盈利",
    "饱满",
    "加速",
    "扩张",
    "中标",
    "回购",
    "分红",
    "修复",
    "反弹",
    "看好",
    "龙头",
    "受益",
)

_NEGATIVE_WORDS = (
    "下滑",
    "亏损",
    "风险",
    "不及预期",
    "减持",
    "利空",
    "收紧",
    "价格战",
    "下调",
    "承压",
    "走弱",
    "暴跌",
    "违约",
    "召回",
    "处罚",
    "调查",
    "退市",
    "萎缩",
    "疲软",
    "担忧",
    "高估",
    "泡沫",
    "限制",
)

_INDUSTRY_TAXONOMY: dict[str, tuple[str, ...]] = {
    "半导体": ("半导体", "芯片", "晶圆", "刻蚀", "光刻", "封测"),
    "新能源": ("新能源", "光伏", "风电", "储能", "锂电", "电池"),
    "汽车": ("汽车", "乘用车", "整车", "新能源车", "智能驾驶", "车企"),
    "白酒": ("白酒", "茅台", "五粮液", "酒企", "次高端"),
    "消费": ("消费", "零售", "食品饮料", "家电", "渠道", "动销"),
    "医药": ("医药", "创新药", "医疗器械", "生物制药", "集采"),
    "银行": ("银行", "信贷", "净息差", "存款"),
    "券商": ("券商", "证券", "投行", "两融"),
    "地产": ("地产", "房地产", "商品房", "房企"),
    "AI算力": ("ai", "算力", "服务器", "光模块", "大模型", "数据中心"),
    "军工": ("军工", "国防", "航空", "导弹"),
    "有色": ("有色", "铜", "铝", "锂", "稀土", "黄金"),
}

_MACRO_TAXONOMY: dict[str, tuple[str, ...]] = {
    "流动性": ("流动性", "mlf", "lpr", "公开市场", "资金面", "净投放", "降准"),
    "利率": ("利率", "降息", "加息", "国债收益率", "美债"),
    "通胀": ("cpi", "ppi", "通胀", "物价"),
    "经济增长": ("gdp", "经济", "pmi", "社融", "工业增加值"),
    "财政政策": ("财政", "专项债", "减税", "补贴"),
    "货币政策": ("央行", "货币政策", "信贷", "货币"),
    "汇率": ("汇率", "人民币", "美元指数"),
    "海外": ("美联储", "关税", "出口", "地缘", "海外"),
}

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[。！？!?])\s*|\n+")


@dataclass
class HeuristicContext:
    title: str
    content: str
    candidate_securities: list[dict]


def _count_terms(text: str, terms: tuple[str, ...]) -> int:
    lowered = text.lower()
    return sum(lowered.count(term.lower()) for term in terms)


def _category_scores(text: str, has_stock_match: bool) -> dict[str, int]:
    scores = {category: _count_terms(text, terms) for category, terms in _CATEGORY_KEYWORDS.items()}
    if has_stock_match:
        scores["stock"] += 3
    return scores


def _sentiment_counts(text: str) -> tuple[int, int]:
    return _count_terms(text, _POSITIVE_WORDS), _count_terms(text, _NEGATIVE_WORDS)


def _score_from_counts(pos: int, neg: int) -> float:
    total = pos + neg
    if total == 0:
        return 0.0
    return clamp((pos - neg) / (total + 2) * 1.5, -0.85, 0.85)


def _sentences(text: str) -> list[str]:
    parts = [part.strip() for part in _SENTENCE_SPLIT_RE.split(text) if part.strip()]
    return parts


def _summary(title: str, content: str) -> str:
    sentences = _sentences(content)
    if not sentences:
        return truncate(title, 160)
    merged = ""
    for sentence in sentences[:2]:
        if len(merged) + len(sentence) > 160:
            break
        merged = f"{merged}{sentence}"
    return truncate(merged or sentences[0], 180)


def _find_mentions(
    text: str,
    candidate_securities: list[dict],
) -> tuple[list[StockMention], list[IndustryMention], list[MacroMention]]:
    lowered = text.lower()
    stocks: list[StockMention] = []
    seen_codes: set[str] = set()

    for candidate in candidate_securities:
        name = str(candidate.get("name") or "").strip()
        code = str(candidate.get("code") or "").strip()
        if not name and not code:
            continue
        aliases = [name, *[str(a) for a in candidate.get("aliases") or [] if a]]
        aliases = [alias for alias in aliases if alias and len(alias) >= 2]
        symbol = code.split(".")[0] if code else ""
        hits = sum(lowered.count(alias.lower()) for alias in aliases)
        if symbol and len(symbol) >= 6 and symbol in lowered:
            hits += 1
        if hits <= 0:
            continue
        key = code or name
        if key in seen_codes:
            continue
        seen_codes.add(key)

        alias = next((a for a in aliases if a.lower() in lowered), name)
        index = lowered.find(alias.lower())
        window = text[max(0, index - 120) : index + 240] if index >= 0 else text
        pos, neg = _sentiment_counts(window)
        stocks.append(
            StockMention(
                code=code or None,
                name=name or code,
                relevance=round(min(1.0, 0.6 + 0.1 * hits), 2),
                sentiment=round(_score_from_counts(pos, neg), 2),
            )
        )

    industries: list[IndustryMention] = []
    for canonical, aliases in _INDUSTRY_TAXONOMY.items():
        hits = _count_terms(lowered, aliases)
        if hits:
            industries.append(
                IndustryMention(name=canonical, relevance=round(min(1.0, 0.55 + 0.1 * hits), 2))
            )

    macros: list[MacroMention] = []
    for tag, aliases in _MACRO_TAXONOMY.items():
        hits = _count_terms(lowered, aliases)
        if hits:
            macros.append(MacroMention(tag=tag, relevance=round(min(1.0, 0.55 + 0.1 * hits), 2)))

    industries.sort(key=lambda item: item.relevance, reverse=True)
    macros.sort(key=lambda item: item.relevance, reverse=True)
    return stocks[:6], industries[:5], macros[:5]


def _direction(score: float) -> str:
    if score >= 0.12:
        return "bullish"
    if score <= -0.12:
        return "bearish"
    return "neutral"


def _opinion(category: str, direction: str) -> str:
    if direction == "bullish":
        base = "边际偏多，关注后续数据验证与预期差。"
    elif direction == "bearish":
        base = "边际偏空，注意风险释放节奏与仓位控制。"
    else:
        base = "影响偏中性，等待更明确的催化信号。"
    if category == "stock":
        return base + "跟踪业绩兑现与估值匹配度。"
    if category == "industry":
        return base + "跟踪产业链订单、价格与库存变化。"
    return base + "跟踪政策落地节奏与流动性变化。"


def _confidence(content: str, signal_count: int) -> float:
    length = len(content)
    if length < 80:
        return 0.3
    value = 0.32 + min(0.25, length / 6000) + min(0.2, signal_count * 0.04)
    return round(min(0.85, value), 2)


def analyze_heuristic(
    *,
    title: str,
    content: str,
    candidate_securities: list[dict] | None = None,
    published_at: datetime | None = None,
) -> ReportAnalysisResult:
    candidates = candidate_securities or []
    text = normalize_text(f"{title}\n{content}")
    stock_mentions, industry_mentions, macro_mentions = _find_mentions(text, candidates)

    category_scores = _category_scores(text, has_stock_match=bool(stock_mentions))
    ranked = sorted(category_scores.items(), key=lambda kv: kv[1], reverse=True)
    primary = ranked[0][0]
    if ranked[0][1] == 0 and ranked[1][1] == 0 and ranked[2][1] == 0:
        macro_hint = any(tag in text.lower() for tag in ("央行", "政策", "经济"))
        primary = "macro" if macro_hint else "industry"

    top_score = ranked[0][1] if ranked[0][1] > 0 else max(1, ranked[0][1])
    categories = [primary]
    for category, value in ranked[1:]:
        if value > 0 and value >= top_score * 0.5 and category not in categories:
            categories.append(category)
            break

    pos, neg = _sentiment_counts(text)
    score = _score_from_counts(pos, neg)
    if primary == "macro":
        score = round(score * 0.7, 2)
    elif primary == "industry":
        score = round(score * 0.85, 2)

    keywords = extract_keywords(text, limit=10)
    sentences = _sentences(content)
    key_points = [truncate(sentence, 90) for sentence in sentences[:3] if len(sentence) >= 8]

    rationale = (
        f"规则引擎：正向信号 {pos} 个、负向信号 {neg} 个；"
        f"类别关键词计数 stock={category_scores['stock']}、"
        f"industry={category_scores['industry']}、macro={category_scores['macro']}。"
    )

    return ReportAnalysisResult(
        primary_category=primary,  # type: ignore[arg-type]
        categories=categories,  # type: ignore[arg-type]
        score=round(score, 3),
        confidence=_confidence(text, pos + neg),
        direction=_direction(score),  # type: ignore[arg-type]
        horizon="short" if primary == "stock" else "medium",
        summary=_summary(title, content),
        opinion=_opinion(primary, _direction(score)),
        key_points=key_points,
        keywords=keywords,
        stock_mentions=stock_mentions,
        industry_mentions=industry_mentions,
        macro_mentions=macro_mentions,
        rationale=rationale,
    )
