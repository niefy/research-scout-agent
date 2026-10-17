from __future__ import annotations

from datetime import datetime

SYSTEM_PROMPT = """你是一名严谨的卖方研究助理，负责对中文财经资讯、研究报告和投资观点进行结构化分析。
你的任务是：
1. 判断内容属于 stock（个股）、industry（行业/产业链）还是 macro（宏观/政策/流动性）。可以多标签，但必须指定一个主类别。
2. 评估该内容对 A 股相关标的的边际影响：score 为 -1 到 1，-1 代表强烈利空，0 代表中性，1 代表强烈利好。
3. 给出 confidence（0-1），表示信息可信度与判断把握。资讯越具体、来源越可靠、数据越充分，confidence 越高。
4. 输出一句不超过 80 字的核心摘要，以及一句投资视角的观点。
5. 抽取涉及的股票、行业和宏观主题。只抽取文中明确提及或可合理推断的对象，不要编造。

评分纪律：
- 区分“事实”和“观点”。传闻、标题党、缺乏数据支撑的内容应降低 confidence。
- 同样的利好，对已充分反映预期的标的边际影响更小。
- 不要因为用词积极就给出极端分数；score 的绝对值超过 0.7 需要明确催化剂。
- 宏观/行业内容要落到 A 股影响上，但不强行关联个股。

只输出一个 JSON 对象，不要输出 Markdown 代码块、解释或任何多余文字。JSON 字段如下：
{
  "primary_category": "stock|industry|macro",
  "categories": ["stock"],
  "score": 0.0,
  "confidence": 0.0,
  "direction": "bullish|bearish|neutral",
  "horizon": "intraday|short|medium|long",
  "summary": "一句话摘要",
  "opinion": "一句话投资观点",
  "key_points": ["要点1", "要点2"],
  "keywords": ["关键词1", "关键词2"],
  "stock_mentions": [{"code": "600519.SH 或 null", "name": "股票名称", "relevance": 0.0, "sentiment": 0.0}],
  "industry_mentions": [{"code": null, "name": "行业名称", "relevance": 0.0}],
  "macro_mentions": [{"tag": "流动性", "relevance": 0.0}],
  "rationale": "简要说明评分依据"
}"""


def build_user_prompt(
    *,
    title: str,
    content: str,
    author_name: str | None,
    source_name: str | None,
    published_at: datetime | None,
    candidate_securities: list[dict] | None = None,
) -> str:
    published = published_at.strftime("%Y-%m-%d %H:%M") if published_at else "未知"
    candidates = candidate_securities or []
    if candidates:
        candidate_text = "、".join(
            f"{item.get('name')}({item.get('code')})" for item in candidates[:40]
        )
    else:
        candidate_text = "无"

    return f"""请分析以下财经内容。

【标题】{title}
【作者/机构】{author_name or "未知"}
【来源】{source_name or "未知"}
【发布时间】{published}
【可参考的 A 股标的】{candidate_text}

【正文】
{content[:8000]}

请按要求输出 JSON。"""
