from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from app.collectors.base import (
    ChannelAdapter,
    RawItem,
    extract_article_body,
    fetch_json,
    fetch_text,
    html_to_text,
    make_http_client,
    map_limited,
)

SHANGHAI = ZoneInfo("Asia/Shanghai")
ROLL_URL = "https://feed.mix.sina.com.cn/api/roll/get"


class SinaAdapter(ChannelAdapter):
    key = "sina"
    display_name = "新浪财经"
    default_config = {
        "pageid": 153,
        # 2516: 财经滚动；2517: 股票；2518: 美股
        "lids": [2516, 2517],
        "num_per_lid": 30,
        "fetch_detail": True,
        "detail_limit": 20,
    }

    async def fetch(
        self,
        client: httpx.AsyncClient,
        config: dict[str, Any],
        limit: int,
    ) -> list[RawItem]:
        merged = self.merged_config(config)
        pageid = merged.get("pageid", 153)
        lids = merged.get("lids") or [2516]
        per_lid = max(1, min(int(merged.get("num_per_lid", 30)), limit))

        items: list[RawItem] = []
        seen: set[str] = set()
        for lid in lids:
            payload = await fetch_json(
                client,
                ROLL_URL,
                params={
                    "pageid": pageid,
                    "lid": lid,
                    "k": "",
                    "num": per_lid,
                    "page": 1,
                },
                headers={"Referer": "https://finance.sina.com.cn/"},
            )
            for entry in (payload.get("result") or {}).get("data") or []:
                item = self._parse_entry(entry)
                if item is None or item.external_id in seen:
                    continue
                seen.add(item.external_id)
                items.append(item)
                if len(items) >= limit:
                    break
            if len(items) >= limit:
                break

        if merged.get("fetch_detail", True) and items:
            detail_limit = min(int(merged.get("detail_limit", 20)), len(items))
            head = await map_limited(items[:detail_limit], self._fetch_detail, concurrency=4)
            items = head + items[detail_limit:]

        return items[:limit]

    def _parse_entry(self, entry: dict[str, Any]) -> RawItem | None:
        title = (entry.get("title") or entry.get("stitle") or "").strip()
        url = (entry.get("url") or entry.get("wapurl") or "").strip()
        if not title or not url:
            return None

        content = html_to_text(entry.get("intro") or entry.get("summary") or "")
        published_at = None
        raw_time = entry.get("ctime") or entry.get("intime")
        if raw_time:
            try:
                published_at = datetime.fromtimestamp(int(raw_time), tz=SHANGHAI).astimezone(
                    UTC
                )
            except (TypeError, ValueError, OSError):
                published_at = None

        author_name = (entry.get("media_name") or entry.get("author") or "").strip() or None
        keywords = [
            word.strip()
            for word in (entry.get("keywords") or "").replace("，", ",").split(",")
            if word.strip()
        ]

        return RawItem(
            external_id=str(entry.get("docid") or entry.get("oid") or url),
            url=url,
            title=title,
            content=content,
            published_at=published_at,
            author_name=author_name,
            source_name=author_name,
            keywords=keywords,
            meta={
                "lid": entry.get("lids") or entry.get("lid"),
                "media_id": entry.get("mediaid"),
                "channel": "sina",
            },
        )

    async def _fetch_detail(self, item: RawItem) -> RawItem:
        # Skip items whose intro is already long enough to analyze.
        if len(item.content) >= 300:
            return item
        async with make_http_client() as client:
            html = await fetch_text(client, item.url)
        body = extract_article_body(html, "artibody")
        if body:
            item.content = body
        return item


__all__ = ["SinaAdapter"]
