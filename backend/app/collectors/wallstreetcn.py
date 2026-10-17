from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx

from app.collectors.base import (
    ChannelAdapter,
    RawItem,
    fetch_json,
    html_to_text,
    make_http_client,
    map_limited,
)

LIST_URL = "https://api-one.wallstcn.com/apiv1/content/articles"
DETAIL_URL = "https://api-one.wallstcn.com/apiv1/content/articles/{article_id}"


class WallStreetCNAdapter(ChannelAdapter):
    key = "wallstreetcn"
    display_name = "华尔街见闻"
    default_config = {
        "channel": "global",
        "fetch_detail": True,
        "detail_limit": 15,
        "detail_min_chars": 200,
    }

    async def fetch(
        self,
        client: httpx.AsyncClient,
        config: dict[str, Any],
        limit: int,
    ) -> list[RawItem]:
        merged = self.merged_config(config)
        payload = await fetch_json(
            client,
            LIST_URL,
            params={
                "channel": merged.get("channel", "global"),
                "limit": min(limit, 100),
                "accept": "article",
            },
            headers={"Referer": "https://wallstreetcn.com/"},
        )
        entries = ((payload.get("data") or {}).get("items")) or []
        items = [item for entry in entries if (item := self._parse_entry(entry)) is not None]
        items = items[:limit]

        if merged.get("fetch_detail", True) and items:
            detail_limit = min(int(merged.get("detail_limit", 15)), len(items))
            min_chars = int(merged.get("detail_min_chars", 200))
            candidates = [item for item in items[:detail_limit] if len(item.content) < min_chars]
            enriched = await map_limited(candidates, self._fetch_detail, concurrency=4)
            by_id = {entry.external_id: entry for entry in enriched}
            items = [by_id.get(entry.external_id, entry) for entry in items]

        return items

    def _parse_entry(self, entry: dict[str, Any]) -> RawItem | None:
        title = (entry.get("title") or "").strip()
        url = (entry.get("uri") or "").strip()
        if not title or not url:
            return None

        author = entry.get("author") or {}
        author_name = (
            (entry.get("source_name") or "").strip()
            or (author.get("display_name") or "").strip()
            or None
        )
        raw_time = entry.get("display_time")
        published_at = None
        if raw_time:
            try:
                published_at = datetime.fromtimestamp(int(raw_time), tz=UTC)
            except (TypeError, ValueError, OSError):
                published_at = None

        content = html_to_text(entry.get("content_short") or "")
        categories = entry.get("categories") or []
        category_keys = [
            c.get("key") if isinstance(c, dict) else str(c) for c in categories if c
        ]

        return RawItem(
            external_id=str(entry.get("id") or url),
            url=url,
            title=title,
            content=content,
            published_at=published_at,
            author_name=author_name,
            author_external_id=str(author.get("id")) if author.get("id") else None,
            author_profile_url=author.get("uri"),
            source_name=author_name,
            engagement={
                "comments": int(entry.get("comment_count") or 0),
                "views": int(entry.get("pageviews") or 0),
            },
            meta={
                "categories": category_keys,
                "editor": author.get("display_name"),
                "tags": [t.get("name") for t in entry.get("tags") or [] if isinstance(t, dict)],
                "symbols": entry.get("symbols") or [],
                "channel": "wallstreetcn",
            },
        )

    async def _fetch_detail(self, item: RawItem) -> RawItem:
        async with make_http_client() as client:
            payload = await fetch_json(
                client,
                DETAIL_URL.format(article_id=item.external_id),
                params={"accept": "article", "extract": 0},
                headers={"Referer": "https://wallstreetcn.com/"},
            )
        data = payload.get("data") or {}
        content = html_to_text(data.get("content") or "")
        if content:
            item.content = content
        if not item.author_external_id:
            author = data.get("author") or {}
            if author.get("id"):
                item.author_external_id = str(author["id"])
            if not item.author_name and author.get("display_name"):
                item.author_name = author["display_name"]
                item.source_name = item.author_name
        return item


__all__ = ["WallStreetCNAdapter"]
