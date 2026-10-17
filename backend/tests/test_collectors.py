from __future__ import annotations

from app.collectors.base import extract_article_body, html_to_text
from app.collectors.sina import SinaAdapter
from app.collectors.wallstreetcn import WallStreetCNAdapter


def test_sina_parse_entry():
    item = SinaAdapter()._parse_entry(
        {
            "title": "央行开展MLF操作",
            "url": "https://finance.sina.com.cn/example.shtml",
            "intro": "净投放流动性。",
            "ctime": "1792225456",
            "docid": "comos:abc",
            "media_name": "环球市场播报",
            "keywords": "央行,流动性",
        }
    )
    assert item is not None
    assert item.external_id == "comos:abc"
    assert item.author_name == "环球市场播报"
    assert item.published_at is not None
    assert item.keywords == ["央行", "流动性"]


def test_wallstreetcn_parse_entry_prefers_source_name():
    item = WallStreetCNAdapter()._parse_entry(
        {
            "id": 123,
            "title": "付鹏说",
            "uri": "https://wallstreetcn.com/premium/articles/123",
            "source_name": "付鹏",
            "author": {"id": 9, "display_name": "编辑", "uri": "https://wallstreetcn.com/authors/9"},
            "display_time": 1792228750,
            "content_short": "内容摘要",
            "categories": [{"key": "shares"}],
        }
    )
    assert item is not None
    assert item.author_name == "付鹏"
    assert item.author_external_id == "9"
    assert item.meta["categories"] == ["shares"]


def test_extract_article_body_stops_at_matching_div():
    html = """
    <html><body>
      <div class="article" id="artibody">
        <h2>标题</h2>
        <p>第一段。</p>
        <div>嵌套内容</div>
        <script>bad()</script>
      </div>
      <div id="footer">页脚不应出现</div>
    </body></html>
    """
    text = extract_article_body(html, "artibody")
    assert "第一段" in text
    assert "嵌套内容" in text
    assert "页脚不应出现" not in text
    assert "bad()" not in text


def test_html_to_text_strips_markup():
    assert html_to_text("<p>收入<b>增长</b>。</p><p>利润提升。</p>") == "收入 增长 。\n利润提升。"
