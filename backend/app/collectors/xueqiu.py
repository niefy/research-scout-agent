from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any

import httpx

from app.collectors.base import (
    AuthorTarget,
    ChannelAdapter,
    CollectError,
    CredentialsMissingError,
    RawItem,
    fetch_json,
    html_to_text,
)
from app.core.config import settings

TIMELINE_URL = "https://xueqiu.com/v4/statuses/user_timeline.json"
DEFAULT_SECRET_REF = "XUEQIU_COOKIE"


class XueqiuAdapter(ChannelAdapter):
    """Xueqiu author timeline adapter.

    Xueqiu has no usable public channel feed for our purposes, so this adapter
    intentionally supports author timelines only.
    """

    key = "xueqiu"
    display_name = "雪球"
    default_config = {
        "secret_ref": DEFAULT_SECRET_REF,
        "author_only": True,
        "count": 20,
    }
    supports_channel_feed = False
    supports_author_feed = True

    async def fetch(
        self,
        client: httpx.AsyncClient,
        config: dict[str, Any],
        limit: int,
    ) -> list[RawItem]:
        raise CollectError("xueqiu only supports author timelines")

    async def fetch_author(
        self,
        client: httpx.AsyncClient,
        config: dict[str, Any],
        target: AuthorTarget,
        limit: int,
    ) -> list[RawItem]:
        merged = self.merged_config(config)
        cookie = self._resolve_cookie(merged)
        count = min(max(1, limit), int(merged.get("count", 20)), 20)
        try:
            payload = await fetch_json(
                client,
                TIMELINE_URL,
                params={
                    "user_id": target.external_id,
                    "page": 1,
                    "count": count,
                },
                headers={
                    "Cookie": cookie,
                    "Referer": target.profile_url
                    or f"https://xueqiu.com/u/{target.external_id}",
                    "X-Requested-With": "XMLHttpRequest",
                },
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in (401, 403):
                raise CredentialsMissingError(
                    "xueqiu credentials rejected (401/403)"
                ) from exc
            raise

        entries = self._extract_entries(payload)
        items: list[RawItem] = []
        for entry in entries:
            item = self._parse_entry(entry, target)
            if item is not None:
                items.append(item)
            if len(items) >= limit:
                break
        return items

    def _resolve_cookie(self, config: dict[str, Any]) -> str:
        cookie = (settings.xueqiu_cookie or "").strip()
        if cookie:
            return cookie
        secret_ref = str(config.get("secret_ref") or DEFAULT_SECRET_REF).strip()
        cookie = (os.environ.get(secret_ref) or "").strip()
        if cookie:
            return cookie
        raise CredentialsMissingError(
            f"xueqiu cookie is not configured (set {secret_ref})"
        )

    def _extract_entries(self, payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [entry for entry in payload if isinstance(entry, dict)]
        if not isinstance(payload, dict):
            return []
        # The timeline endpoint has returned both shapes over time.
        entries = payload.get("statuses")
        if entries is None:
            entries = payload.get("list")
        if entries is None:
            entries = (payload.get("data") or {}).get("statuses")
        if not isinstance(entries, list):
            return []
        return [entry for entry in entries if isinstance(entry, dict)]

    def _parse_entry(
        self,
        entry: dict[str, Any],
        target: AuthorTarget,
    ) -> RawItem | None:
        status_id = entry.get("id")
        if status_id is None:
            return None

        text = html_to_text(
            str(entry.get("description") or entry.get("text") or entry.get("title") or "")
        )
        title = (entry.get("title") or "").strip()
        if not title:
            title = text.splitlines()[0].strip() if text else ""
        if not title:
            return None
        if len(title) > 120:
            title = f"{title[:117]}..."

        user = entry.get("user") if isinstance(entry.get("user"), dict) else {}
        user_id = str(user.get("id") or target.external_id)
        screen_name = (
            str(user.get("screen_name") or "").strip()
            or target.display_name
            or user_id
        )
        profile_url = target.profile_url or f"https://xueqiu.com/u/{user_id}"

        url = str(entry.get("url") or "").strip()
        if not url:
            path = str(entry.get("target") or "").strip()
            if path.startswith("/"):
                url = f"https://xueqiu.com{path}"
            else:
                url = f"https://xueqiu.com/{user_id}/{status_id}"

        engagement = {
            "views": _as_int(entry.get("view_count")),
            "comments": _as_int(entry.get("reply_count")),
            "likes": _as_int(entry.get("fav_count")),
            "reposts": _as_int(entry.get("retweet_count")),
        }

        return RawItem(
            external_id=str(status_id),
            url=url,
            title=title,
            content=text,
            published_at=_parse_created_at(entry.get("created_at")),
            author_name=screen_name,
            author_external_id=user_id,
            author_profile_url=profile_url,
            source_name="雪球",
            engagement={key: value for key, value in engagement.items() if value},
            meta={
                "channel": "xueqiu",
                "is_retweet": bool(entry.get("retweeted_status")),
                "target_author_id": target.external_id,
            },
        )


def _parse_created_at(value: Any) -> datetime | None:
    try:
        timestamp = int(value)
    except (TypeError, ValueError):
        return None
    # Xueqiu returns milliseconds.
    if timestamp > 10_000_000_000:
        timestamp //= 1000
    try:
        return datetime.fromtimestamp(timestamp, tz=UTC)
    except (OSError, ValueError, OverflowError):
        return None


def _as_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


__all__ = ["XueqiuAdapter"]
