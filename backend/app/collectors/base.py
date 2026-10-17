from __future__ import annotations

import asyncio
import html as html_lib
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from html.parser import HTMLParser
from typing import Any

import httpx
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.config import settings

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)

_SCRIPT_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_SPACE_RE = re.compile(r"[ \t\r\f\v]+")
_NEWLINE_RE = re.compile(r"\n{3,}")


class CollectError(RuntimeError):
    pass


@dataclass
class RawItem:
    external_id: str
    url: str
    title: str
    content: str = ""
    published_at: datetime | None = None
    author_name: str | None = None
    author_external_id: str | None = None
    author_profile_url: str | None = None
    source_name: str | None = None
    keywords: list[str] = field(default_factory=list)
    engagement: dict[str, int] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)

    def normalized_published_at(self) -> datetime:
        if self.published_at is None:
            return datetime.now(UTC)
        if self.published_at.tzinfo is None:
            return self.published_at.replace(tzinfo=UTC)
        return self.published_at.astimezone(UTC)


def html_to_text(value: str) -> str:
    if not value:
        return ""
    value = _SCRIPT_RE.sub(" ", value)
    value = re.sub(r"<br\s*/?>", "\n", value, flags=re.IGNORECASE)
    value = re.sub(r"</p>|</div>|</h[1-6]>|</li>", "\n", value, flags=re.IGNORECASE)
    value = _TAG_RE.sub(" ", value)
    value = html_lib.unescape(value)
    value = _SPACE_RE.sub(" ", value)
    value = "\n".join(line.strip() for line in value.splitlines())
    return _NEWLINE_RE.sub("\n\n", value).strip()


class _BodyParser(HTMLParser):
    """Collect visible text of the first element matching a div id/class."""

    def __init__(self, target_id: str | None = None, target_class: str | None = None):
        super().__init__(convert_charrefs=True)
        self.target_id = target_id
        self.target_class = target_class
        self.depth = 0
        self.started = False
        self.done = False
        self.skip_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = dict(attrs)
        if not self.started:
            matches_id = self.target_id and attr.get("id") == self.target_id
            classes = (attr.get("class") or "").split()
            matches_class = self.target_class and self.target_class in classes
            if (matches_id or matches_class) and tag == "div":
                self.started = True
                self.depth = 1
            return

        if tag == "div":
            self.depth += 1
        if tag in {"script", "style"}:
            self.skip_depth += 1
        if tag in {"p", "div", "br", "h1", "h2", "h3", "h4", "li", "blockquote"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if not self.started or self.done:
            return
        if tag in {"script", "style"} and self.skip_depth:
            self.skip_depth -= 1
        if tag in {"p", "div", "h1", "h2", "h3", "h4", "li", "blockquote"}:
            self.parts.append("\n")
        if tag == "div":
            self.depth -= 1
            if self.depth <= 0:
                self.done = True

    def handle_data(self, data: str) -> None:
        if self.started and not self.done and self.skip_depth == 0:
            self.parts.append(data)

    def text(self) -> str:
        raw = "".join(self.parts)
        raw = _SPACE_RE.sub(" ", raw)
        raw = "\n".join(line.strip() for line in raw.splitlines())
        return _NEWLINE_RE.sub("\n\n", raw).strip()


def extract_article_body(html: str, element_id: str) -> str:
    parser = _BodyParser(target_id=element_id)
    try:
        parser.feed(html)
    except Exception:
        return ""
    return parser.text()


def make_http_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=httpx.Timeout(settings.crawl_request_timeout),
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.6",
        },
        follow_redirects=True,
    )


async def request_with_retry(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    attempts: int = 3,
    **kwargs: Any,
) -> httpx.Response:
    async for attempt in AsyncRetrying(
        stop=stop_after_attempt(attempts),
        wait=wait_exponential(multiplier=0.6, min=0.6, max=6),
        retry=retry_if_exception_type((httpx.TransportError, httpx.HTTPStatusError)),
        reraise=True,
    ):
        with attempt:
            response = await client.request(method, url, **kwargs)
            if response.status_code >= 500 or response.status_code == 429:
                response.raise_for_status()
            response.raise_for_status()
            return response
    raise CollectError(f"request failed: {url}")


async def fetch_json(client: httpx.AsyncClient, url: str, **kwargs: Any) -> Any:
    response = await request_with_retry(client, "GET", url, **kwargs)
    try:
        return response.json()
    except ValueError as exc:
        raise CollectError(f"invalid JSON from {url}") from exc


async def fetch_text(client: httpx.AsyncClient, url: str, **kwargs: Any) -> str:
    response = await request_with_retry(client, "GET", url, **kwargs)
    return response.text


async def map_limited(
    items: list[RawItem],
    func,
    *,
    concurrency: int = 5,
) -> list[RawItem]:
    semaphore = asyncio.Semaphore(concurrency)

    async def run(item: RawItem) -> RawItem:
        async with semaphore:
            try:
                return await func(item)
            except Exception:
                return item

    return list(await asyncio.gather(*(run(item) for item in items)))


class ChannelAdapter(ABC):
    key: str
    display_name: str
    default_config: dict[str, Any] = {}

    @abstractmethod
    async def fetch(
        self,
        client: httpx.AsyncClient,
        config: dict[str, Any],
        limit: int,
    ) -> list[RawItem]:
        raise NotImplementedError

    async def enrich(self, client: httpx.AsyncClient, item: RawItem) -> RawItem:
        return item

    def merged_config(self, config: dict[str, Any] | None) -> dict[str, Any]:
        merged = dict(self.default_config)
        merged.update(config or {})
        return merged
