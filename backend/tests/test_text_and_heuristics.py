from __future__ import annotations

from app.agents.heuristics import analyze_heuristic
from app.scoring.text import (
    clean_text,
    content_hash,
    extract_keywords,
    hamming_distance,
    normalize_text,
    simhash64,
)


def test_clean_text_preserves_chinese_punctuation():
    assert clean_text("  <p>营收增长，利润率提升。</p> ") == "营收增长，利润率提升。"


def test_normalize_text_folds_fullwidth_forms():
    assert normalize_text("Ａ股１２３，增长") == "A股123,增长"


def test_content_hash_is_stable_and_sensitive():
    first = content_hash("标题", "正文")
    assert first == content_hash("  标题 ", "<p>正文</p>")
    assert first != content_hash("标题", "不同的正文")


def test_simhash_near_duplicates_are_close():
    a = simhash64("贵州茅台发布三季报，营收同比增长12%，直营渠道占比提升")
    b = simhash64("贵州茅台发布三季报，营收同比增长12.1%，直营渠道占比继续提升")
    c = simhash64("央行开展MLF操作，市场流动性保持合理充裕")
    assert hamming_distance(a, b) < 12
    assert hamming_distance(a, c) > 12


def test_extract_keywords_returns_meaningful_terms():
    keywords = extract_keywords("半导体设备国产化加速，半导体设备订单饱满，国产替代提升")
    assert any("半导体" in word for word in keywords)
    assert len(keywords) <= 8


def test_heuristic_stock_analysis_uses_candidate_security():
    result = analyze_heuristic(
        title="贵州茅台三季度营收同比增长12%",
        content="贵州茅台发布三季报，营收同比增长12%，归母净利润同比增长13%，机构维持买入评级。",
        candidate_securities=[
            {"code": "600519.SH", "name": "贵州茅台", "aliases": ["茅台"]},
        ],
    )
    assert result.primary_category == "stock"
    assert result.score > 0
    assert result.direction == "bullish"
    assert result.stock_mentions[0].code == "600519.SH"
    assert "茅台" in result.summary or "茅台" in result.keywords[0]


def test_heuristic_macro_analysis():
    result = analyze_heuristic(
        title="央行开展MLF操作",
        content="中国人民银行开展6000亿元中期借贷便利操作，净投放流动性，市场资金面保持平稳。",
    )
    assert result.primary_category == "macro"
    assert any(tag.tag == "流动性" for tag in result.macro_mentions)


def test_heuristic_bearish_signal():
    result = analyze_heuristic(
        title="某公司业绩大幅下滑",
        content="公司发布业绩预告，净利润大幅下滑，机构下调评级，存在退市风险。",
    )
    assert result.score < 0
    assert result.direction == "bearish"
