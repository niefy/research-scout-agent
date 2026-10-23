from __future__ import annotations

from app.agents.schemas import IndustryMention, ReportAnalysisResult, StockMention
from app.models.personalization import AuthorFollow
from app.models.report import ReportAnalysis
from app.services import analysis as analysis_service
from app.services import stocks as stock_service
from app.services.feedback import remove_report_feedback, set_report_feedback
from tests.factories import (
    add_author,
    add_channel,
    add_report,
    add_security,
    add_user,
)


async def _entry(db_session, report):
    analysis = (
        await db_session.get(ReportAnalysis, report.current_analysis_id)
        if report.current_analysis_id
        else None
    )
    return stock_service.PoolEntry(
        report=report, author=None, follow=None, analysis=analysis
    )


async def test_direct_mention_beats_industry_and_macro(db_session):
    channel = await add_channel(db_session, code="mock")
    security = await add_security(
        db_session, code="600519.SH", name="贵州茅台", industry_code="SW_FOOD"
    )
    report = await add_report(
        db_session,
        channel,
        title="茅台与白酒行业周报",
        primary_category="industry",
        categories=["stock", "industry", "macro"],
        industry_codes=["SW_FOOD"],
        stock_mentions=[
            {
                "code": "600519.SH",
                "name": "贵州茅台",
                "sentiment": 0.4,
                "relevance": 0.9,
            }
        ],
        macro_mentions=[{"tag": "流动性", "relevance": 0.8}],
    )

    match = stock_service._match_report(await _entry(db_session, report), security)

    assert match is not None
    assert match.relation == "stock"
    assert match.reason == "direct_mention"
    assert match.score == 0.4
    assert match.relevance == 0.9


async def test_stock_code_fallback_is_still_stock_relation(db_session):
    channel = await add_channel(db_session, code="mock")
    security = await add_security(db_session, code="600519.SH", name="贵州茅台")
    report = await add_report(
        db_session,
        channel,
        title="白酒动销跟踪",
        primary_category="macro",
        categories=["macro"],
        stock_codes=["600519.SH"],
        macro_mentions=[{"tag": "消费", "relevance": 0.8}],
    )

    match = stock_service._match_report(await _entry(db_session, report), security)

    assert match is not None
    assert match.relation == "stock"
    assert match.reason == "stock_code_fallback"
    assert match.relevance == 0.7


async def test_industry_report_only_matches_stocks_in_that_industry(db_session):
    channel = await add_channel(db_session, code="mock")
    bank = await add_security(
        db_session, code="600036.SH", name="招商银行", industry_code="SW_BANK"
    )
    chip = await add_security(
        db_session, code="688981.SH", name="中芯国际", industry_code="SW_CHIP"
    )
    report = await add_report(
        db_session,
        channel,
        title="银行业净息差跟踪",
        primary_category="industry",
        categories=["industry"],
        industry_codes=["SW_BANK"],
    )
    entry = await _entry(db_session, report)

    bank_match = stock_service._match_report(entry, bank)
    chip_match = stock_service._match_report(entry, chip)

    assert bank_match is not None
    assert bank_match.relation == "industry"
    assert chip_match is None


async def test_a_stock_article_counts_only_once_for_that_stock(db_session):
    channel = await add_channel(db_session, code="mock")
    user = await add_user(db_session)
    author = await add_author(db_session, name="张分析", is_curated=True)
    security = await add_security(
        db_session, code="600519.SH", name="贵州茅台", industry_code="SW_FOOD"
    )
    await add_report(
        db_session,
        channel,
        author=author,
        title="茅台三季报点评",
        primary_category="stock",
        categories=["stock", "industry"],
        industry_codes=["SW_FOOD"],
        stock_mentions=[
            {
                "code": "600519.SH",
                "name": "贵州茅台",
                "sentiment": 0.6,
                "relevance": 1.0,
            }
        ],
    )

    score = await stock_service.compute_stock_score(
        db_session, user.id, security, scope="hybrid"
    )

    assert score.result.report_count == 1
    assert score.result.relation_counts == {"stock": 1}
    assert score.evidence.stock_count == 1
    assert score.evidence.industry_count == 0
    assert score.evidence.macro_count == 0


async def test_macro_only_evidence_is_labelled_and_warns(db_session):
    channel = await add_channel(db_session, code="mock")
    user = await add_user(db_session)
    author = await add_author(db_session, name="王宏观", is_curated=True)
    security = await add_security(db_session, code="600519.SH", name="贵州茅台")
    await add_report(
        db_session,
        channel,
        author=author,
        title="流动性宽松利好权益资产",
        score=0.5,
        primary_category="macro",
        categories=["macro"],
        macro_mentions=[{"tag": "流动性", "relevance": 0.9}],
    )

    score = await stock_service.compute_stock_score(
        db_session, user.id, security, scope="hybrid"
    )
    payload = stock_service.serialize_stock_score(score)

    assert score.evidence.level == "macro"
    assert score.evidence.is_macro_only is True
    assert payload["display_label"] == "宏观参考"
    assert payload["display_score"] == payload["total_points"]
    assert "宏观参考" in payload["conclusion"]
    assert "缺少个股与行业证据" in payload["conclusion"]
    assert "综合信号" not in payload["conclusion"]


async def test_industry_article_does_not_affect_other_industries(db_session):
    channel = await add_channel(db_session, code="mock")
    user = await add_user(db_session)
    author = await add_author(db_session, name="李产业", is_curated=True)
    bank = await add_security(
        db_session, code="600036.SH", name="招商银行", industry_code="SW_BANK"
    )
    chip = await add_security(
        db_session, code="688981.SH", name="中芯国际", industry_code="SW_CHIP"
    )
    await add_report(
        db_session,
        channel,
        author=author,
        title="银行业净息差跟踪",
        primary_category="industry",
        categories=["industry"],
        industry_codes=["SW_BANK"],
    )

    bank_score = await stock_service.compute_stock_score(
        db_session, user.id, bank, scope="hybrid"
    )
    chip_score = await stock_service.compute_stock_score(
        db_session, user.id, chip, scope="hybrid"
    )

    assert bank_score.evidence.industry_count == 1
    assert bank_score.evidence.level == "industry"
    assert bank_score.display_label == "综合得分"
    assert chip_score.result.report_count == 0
    assert chip_score.evidence.level == "none"
    assert chip_score.display_label == "证据不足"
    assert chip_score.display_score is None


async def test_stock_mentions_do_not_pollute_industry_codes(db_session, monkeypatch):
    channel = await add_channel(db_session, code="mock")
    await add_security(
        db_session, code="600036.SH", name="招商银行", industry_code="SW_BANK"
    )
    industry = analysis_service.Industry(
        code="SW_BANK", name="银行", level=1, enabled=True
    )
    db_session.add(industry)
    await db_session.commit()

    report = await add_report(
        db_session,
        channel,
        title="招商银行三季报点评",
        primary_category="stock",
        categories=["stock"],
        analysis_status="pending",
    )

    stock_only = ReportAnalysisResult(
        primary_category="stock",
        categories=["stock"],
        score=0.6,
        confidence=0.8,
        direction="bullish",
        summary="招商银行盈利改善。",
        stock_mentions=[
            StockMention(code="600036.SH", name="招商银行", sentiment=0.6)
        ],
    )

    async def fake_run_analysis(**kwargs):
        return stock_only, {"model": "fake"}, []

    monkeypatch.setattr(analysis_service, "run_analysis", fake_run_analysis)

    assert await analysis_service.analyze_report(db_session, report) is True
    await db_session.refresh(report)
    # A mentioned stock must not fan out to every peer in its industry.
    assert report.stock_codes == ["600036.SH"]
    assert report.industry_codes == []

    explicit_industry = stock_only.model_copy(
        update={"industry_mentions": [IndustryMention(name="银行", relevance=0.8)]}
    )

    async def fake_run_with_industry(**kwargs):
        return explicit_industry, {"model": "fake"}, []

    monkeypatch.setattr(analysis_service, "run_analysis", fake_run_with_industry)

    assert await analysis_service.analyze_report(db_session, report) is True
    await db_session.refresh(report)
    assert report.industry_codes == ["SW_BANK"]


async def test_scopes_control_the_candidate_pool(db_session):
    channel = await add_channel(db_session, code="mock")
    user = await add_user(db_session)
    followed = await add_author(db_session, name="我关注的作者")
    curated = await add_author(db_session, name="系统精选作者", is_curated=True)
    other = await add_author(db_session, name="其他作者")
    db_session.add(AuthorFollow(user_id=user.id, author_id=followed.id))
    await db_session.commit()

    for author in (followed, curated, other):
        await add_report(
            db_session,
            channel,
            author=author,
            title=f"{author.canonical_name}的报告",
            stock_mentions=[
                {
                    "code": "600519.SH",
                    "name": "贵州茅台",
                    "sentiment": 0.3,
                    "relevance": 0.9,
                }
            ],
        )

    personal = await stock_service.load_report_pool(
        db_session, user.id, scope="personal", window="30d"
    )
    hybrid = await stock_service.load_report_pool(
        db_session, user.id, scope="hybrid", window="30d"
    )
    every = await stock_service.load_report_pool(
        db_session, user.id, scope="all", window="30d"
    )

    assert {entry.author.canonical_name for entry in personal} == {"我关注的作者"}
    assert {entry.author.canonical_name for entry in hybrid} == {
        "我关注的作者",
        "系统精选作者",
    }
    assert {entry.author.canonical_name for entry in every} == {
        "我关注的作者",
        "系统精选作者",
        "其他作者",
    }


async def test_feedback_excludes_and_restores_a_report(db_session):
    channel = await add_channel(db_session, code="mock")
    user = await add_user(db_session)
    author = await add_author(db_session, name="张分析", is_curated=True)
    security = await add_security(db_session, code="600519.SH", name="贵州茅台")
    keep = await add_report(
        db_session,
        channel,
        author=author,
        title="茅台渠道反馈积极",
        stock_mentions=[
            {"code": "600519.SH", "name": "贵州茅台", "sentiment": 0.5}
        ],
    )
    drop = await add_report(
        db_session,
        channel,
        author=author,
        title="白酒板块周报",
        stock_mentions=[
            {"code": "600519.SH", "name": "贵州茅台", "sentiment": -0.5}
        ],
    )

    await set_report_feedback(db_session, user.id, drop.id, security.id)

    excluded = await stock_service.compute_stock_score(
        db_session, user.id, security, scope="hybrid"
    )
    assert excluded.result.report_count == 1
    assert [item.report_id for item in excluded.result.breakdown] == [keep.id]

    assert await remove_report_feedback(db_session, user.id, drop.id, security.id)

    restored = await stock_service.compute_stock_score(
        db_session, user.id, security, scope="hybrid"
    )
    assert restored.result.report_count == 2
    assert {item.report_id for item in restored.result.breakdown} == {keep.id, drop.id}


async def test_default_scope_comes_from_user_config(db_session):
    channel = await add_channel(db_session, code="mock")
    user = await add_user(
        db_session, scoring_config={"default_scope": "personal"}
    )
    followed = await add_author(db_session, name="我关注的作者")
    curated = await add_author(db_session, name="系统精选作者", is_curated=True)
    db_session.add(AuthorFollow(user_id=user.id, author_id=followed.id))
    await db_session.commit()
    for author in (followed, curated):
        await add_report(
            db_session,
            channel,
            author=author,
            title=f"{author.canonical_name}的茅台观点",
            stock_mentions=[
                {"code": "600519.SH", "name": "贵州茅台", "sentiment": 0.4}
            ],
        )
    security = await add_security(db_session, code="600519.SH", name="贵州茅台")

    score = await stock_service.compute_stock_score(
        db_session, user.id, security, scope=None
    )

    assert score.scope == "personal"
    assert score.result.report_count == 1
