from __future__ import annotations

import difflib
import re
import unicodedata

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.author import Author, AuthorAlias, AuthorIdentity
from app.models.channel import Channel
from app.models.personalization import AuthorFollow
from app.schemas.author import AuthorCreate

XUEQIU_CHANNEL_CODE = "xueqiu"
_XUEQIU_ID_RE = re.compile(r"xueqiu\.com/(?:u/)?(\d+)")


class AuthorConflictError(ValueError):
    pass


class AuthorImportError(ValueError):
    pass


def normalize_author_name(name: str) -> str:
    value = unicodedata.normalize("NFKC", name or "").strip().lower()
    value = re.sub(r"[\s·•\-_/|｜]+", "", value)
    value = re.sub(r"[（(].*?[)）]", "", value)
    return value


def infer_author_type(name: str) -> str:
    lowered = name.lower()
    if any(word in name for word in ("证券", "研究", "基金", "资管", "研究院", "研究所", "投顾")):
        return "institution"
    if any(word in name for word in ("日报", "时报", "新闻", "财经", "媒体", "周刊", "电视台")):
        return "media"
    if lowered.startswith("mock-author"):
        return "analyst"
    return "analyst"


async def get_author(session: AsyncSession, author_id: int) -> Author | None:
    return await session.get(Author, author_id)


async def resolve_author(
    session: AsyncSession,
    *,
    channel_id: int,
    raw_name: str | None,
    external_id: str | None = None,
    profile_url: str | None = None,
    create_if_missing: bool = True,
) -> Author | None:
    """Resolve a channel-level author to a global author record.

    Order: channel identity -> alias (channel first) -> canonical name ->
    conservative fuzzy match -> create.
    """
    if external_id:
        identity = await session.scalar(
            select(AuthorIdentity).where(
                AuthorIdentity.channel_id == channel_id,
                AuthorIdentity.external_id == external_id,
            )
        )
        if identity is not None:
            author = await session.get(Author, identity.author_id)
            if author is not None:
                await _touch_identity(session, identity, raw_name, profile_url)
                return author

    name = (raw_name or "").strip()
    if not name:
        return None
    normalized = normalize_author_name(name)
    if not normalized:
        return None

    alias = await session.scalar(
        select(AuthorAlias)
        .where(AuthorAlias.normalized_alias == normalized)
        .order_by(AuthorAlias.channel_id.is_(None), AuthorAlias.confidence.desc())
        .limit(1)
    )
    if alias is not None:
        author = await session.get(Author, alias.author_id)
        if author is not None:
            await _ensure_identity(session, author, channel_id, external_id, name, profile_url)
            return author

    author = await session.scalar(select(Author).where(Author.normalized_name == normalized))
    if author is not None:
        await _ensure_alias(session, author, channel_id, name, source="canonical")
        await _ensure_identity(session, author, channel_id, external_id, name, profile_url)
        return author

    fuzzy = await _fuzzy_match(session, normalized)
    if fuzzy is not None:
        await _ensure_alias(session, fuzzy, channel_id, name, source="fuzzy", confidence=0.8)
        await _ensure_identity(session, fuzzy, channel_id, external_id, name, profile_url)
        return fuzzy

    if not create_if_missing:
        return None

    author = Author(
        canonical_name=name,
        normalized_name=normalized,
        author_type=infer_author_type(name),
        default_weight=1.0,
        meta={"origin": "auto_extracted", "first_channel_id": channel_id},
    )
    session.add(author)
    await session.flush()
    await _ensure_alias(session, author, channel_id, name, source="auto")
    await _ensure_identity(session, author, channel_id, external_id, name, profile_url)
    return author


async def _fuzzy_match(session: AsyncSession, normalized: str) -> Author | None:
    if len(normalized) < 3:
        return None
    prefix = normalized[:2]
    candidates = (
        await session.scalars(
            select(AuthorAlias)
            .where(
                or_(
                    AuthorAlias.normalized_alias.like(f"%{normalized}%"),
                    AuthorAlias.normalized_alias.like(f"{prefix}%"),
                )
            )
            .limit(200)
        )
    ).all()
    matches: list[tuple[float, AuthorAlias]] = []
    for candidate in candidates:
        ratio = difflib.SequenceMatcher(None, normalized, candidate.normalized_alias).ratio()
        if ratio >= 0.9:
            matches.append((ratio, candidate))
    if not matches:
        return None
    matches.sort(key=lambda pair: pair[0], reverse=True)
    best_ratio, best = matches[0]
    if len(matches) > 1 and matches[1][0] == best_ratio:
        return None
    return await session.get(Author, best.author_id)


async def _ensure_alias(
    session: AsyncSession,
    author: Author,
    channel_id: int | None,
    alias: str,
    *,
    source: str,
    confidence: float = 1.0,
) -> None:
    normalized = normalize_author_name(alias)
    if not normalized:
        return
    existing = await session.scalar(
        select(AuthorAlias).where(
            AuthorAlias.author_id == author.id,
            AuthorAlias.normalized_alias == normalized,
            AuthorAlias.channel_id == channel_id,
        )
    )
    if existing is None:
        session.add(
            AuthorAlias(
                author_id=author.id,
                alias=alias.strip(),
                normalized_alias=normalized,
                channel_id=channel_id,
                confidence=confidence,
                source=source,
            )
        )


async def _ensure_identity(
    session: AsyncSession,
    author: Author,
    channel_id: int,
    external_id: str | None,
    name: str | None,
    profile_url: str | None,
) -> None:
    if not external_id:
        return
    existing = await session.scalar(
        select(AuthorIdentity).where(
            AuthorIdentity.channel_id == channel_id,
            AuthorIdentity.external_id == external_id,
        )
    )
    if existing is None:
        session.add(
            AuthorIdentity(
                author_id=author.id,
                channel_id=channel_id,
                external_id=external_id,
                display_name=name,
                profile_url=profile_url,
            )
        )
    else:
        await _touch_identity(session, existing, name, profile_url)


async def _touch_identity(
    session: AsyncSession,
    identity: AuthorIdentity,
    name: str | None,
    profile_url: str | None,
) -> None:
    if name:
        identity.display_name = name
    if profile_url:
        identity.profile_url = profile_url


def parse_xueqiu_external_id(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        raise AuthorImportError("请填写雪球用户 ID 或主页链接")
    if raw.isdigit():
        return raw
    match = _XUEQIU_ID_RE.search(raw)
    if match:
        return match.group(1)
    raise AuthorImportError("无法识别雪球用户 ID，请填写数字 ID 或主页链接")


async def import_xueqiu_author(
    session: AsyncSession,
    *,
    user_id: int,
    external_id: str | None = None,
    profile_url: str | None = None,
    display_name: str | None = None,
    follow: bool = True,
    weight: float = 1.0,
) -> tuple[Author, AuthorFollow | None, bool, bool]:
    """Create or reuse a Xueqiu author and optionally follow it.

    Returns ``(author, follow, created, newly_followed)``. The identity is the
    authority for deduplication; a display-name match only merges authors when
    the existing record has no conflicting Xueqiu identity.
    """
    resolved_external_id = parse_xueqiu_external_id(external_id or profile_url or "")
    channel = await session.scalar(
        select(Channel).where(Channel.code == XUEQIU_CHANNEL_CODE)
    )
    if channel is None:
        raise AuthorImportError("雪球渠道未初始化")
    if not channel.enabled:
        raise AuthorImportError("雪球渠道已停用")

    profile = (profile_url or "").strip() or f"https://xueqiu.com/u/{resolved_external_id}"
    identity = await session.scalar(
        select(AuthorIdentity).where(
            AuthorIdentity.channel_id == channel.id,
            AuthorIdentity.external_id == resolved_external_id,
        )
    )
    created = False
    if identity is not None:
        author = await session.get(Author, identity.author_id)
        if author is None:
            raise AuthorImportError("作者记录不存在")
        await _touch_identity(session, identity, display_name, profile)
    else:
        name = (display_name or "").strip()
        candidate: Author | None = None
        if name:
            candidate = await session.scalar(
                select(Author).where(
                    Author.normalized_name == normalize_author_name(name)
                )
            )
            if candidate is not None:
                conflicting = await session.scalar(
                    select(AuthorIdentity.id).where(
                        AuthorIdentity.author_id == candidate.id,
                        AuthorIdentity.channel_id == channel.id,
                    )
                )
                if conflicting is not None:
                    candidate = None
        if candidate is not None:
            author = candidate
        else:
            if not name:
                name = f"雪球用户{resolved_external_id}"
            normalized = normalize_author_name(name)
            existing = await session.scalar(
                select(Author).where(Author.normalized_name == normalized)
            )
            if existing is not None:
                name = f"{name}（雪球{resolved_external_id}）"
                normalized = normalize_author_name(name)
            author = Author(
                canonical_name=name,
                normalized_name=normalized,
                author_type=infer_author_type(name),
                default_weight=1.0,
                meta={
                    "origin": "user_import",
                    "imported_by_id": user_id,
                    "channel": XUEQIU_CHANNEL_CODE,
                },
            )
            session.add(author)
            await session.flush()
            await _ensure_alias(
                session, author, channel.id, name, source="import"
            )
        session.add(
            AuthorIdentity(
                author_id=author.id,
                channel_id=channel.id,
                external_id=resolved_external_id,
                display_name=display_name or author.canonical_name,
                profile_url=profile,
            )
        )
        created = True

    follow_row: AuthorFollow | None = None
    newly_followed = False
    if follow:
        follow_row = await get_follow(session, user_id, author.id)
        if follow_row is None:
            follow_row = AuthorFollow(
                user_id=user_id,
                author_id=author.id,
                weight=weight,
            )
            session.add(follow_row)
            newly_followed = True
        else:
            follow_row.weight = weight
    await session.commit()
    await session.refresh(author)
    if follow_row is not None:
        await session.refresh(follow_row)
    return author, follow_row, created, newly_followed


async def recommended_authors(
    session: AsyncSession,
    user_id: int,
    *,
    limit: int = 10,
) -> list[dict]:
    followed_ids = select(AuthorFollow.author_id).where(
        AuthorFollow.user_id == user_id
    )
    authors = list(
        (
            await session.scalars(
                select(Author)
                .where(
                    Author.is_curated.is_(True),
                    Author.status == "active",
                    Author.id.not_in(followed_ids),
                )
                .order_by(Author.curated_rank.desc(), Author.id)
                .limit(limit)
            )
        ).all()
    )
    counts: dict[int, int] = {}
    if authors:
        rows = (
            await session.execute(
                select(AuthorFollow.author_id, func.count(AuthorFollow.id))
                .where(AuthorFollow.author_id.in_([author.id for author in authors]))
                .group_by(AuthorFollow.author_id)
            )
        ).all()
        counts = {author_id: count for author_id, count in rows}
    return [
        {
            "id": author.id,
            "canonical_name": author.canonical_name,
            "author_type": author.author_type,
            "quality_score": author.quality_score,
            "sector_tags": author.sector_tags or [],
            "curated_rank": author.curated_rank,
            "last_crawled_at": author.last_crawled_at,
            "follower_count": counts.get(author.id, 0),
        }
        for author in authors
    ]


async def create_author(session: AsyncSession, payload: AuthorCreate, user_id: int) -> Author:
    normalized = normalize_author_name(payload.canonical_name)
    existing = await session.scalar(select(Author).where(Author.normalized_name == normalized))
    if existing is not None:
        raise AuthorConflictError("author already exists")

    author = Author(
        canonical_name=payload.canonical_name.strip(),
        normalized_name=normalized,
        author_type=payload.author_type,
        default_weight=payload.default_weight,
        created_by_id=user_id,
        meta={"origin": "manual"},
    )
    session.add(author)
    await session.flush()
    await _ensure_alias(session, author, None, payload.canonical_name, source="manual")
    for alias in payload.aliases:
        await _ensure_alias(session, author, None, alias, source="manual")
    await session.commit()
    await session.refresh(author)
    return author


async def author_detail(session: AsyncSession, author_id: int) -> dict | None:
    from app.models.report import Report

    author = await session.get(Author, author_id)
    if author is None:
        return None

    aliases = list(
        (
            await session.scalars(
                select(AuthorAlias.alias)
                .where(AuthorAlias.author_id == author_id)
                .order_by(AuthorAlias.id)
            )
        ).all()
    )
    identities = list(
        (
            await session.scalars(
                select(AuthorIdentity)
                .where(AuthorIdentity.author_id == author_id)
                .order_by(AuthorIdentity.id)
            )
        ).all()
    )
    follower_count = await session.scalar(
        select(func.count(AuthorFollow.id)).where(AuthorFollow.author_id == author_id)
    ) or 0
    report_count = await session.scalar(
        select(func.count(Report.id)).where(Report.author_id == author_id)
    ) or 0

    return {
        "id": author.id,
        "canonical_name": author.canonical_name,
        "author_type": author.author_type,
        "default_weight": author.default_weight,
        "status": author.status,
        "is_curated": author.is_curated,
        "curated_rank": author.curated_rank,
        "crawl_enabled": author.crawl_enabled,
        "quality_score": author.quality_score,
        "sector_tags": author.sector_tags or [],
        "last_crawled_at": author.last_crawled_at,
        "crawl_status": author.crawl_status,
        "crawl_error": author.crawl_error,
        "meta": author.meta or {},
        "created_at": author.created_at,
        "aliases": aliases,
        "identities": [
            {
                "id": identity.id,
                "channel_id": identity.channel_id,
                "external_id": identity.external_id,
                "display_name": identity.display_name,
                "profile_url": identity.profile_url,
            }
            for identity in identities
        ],
        "follower_count": follower_count,
        "report_count": report_count,
    }


async def get_follow(session: AsyncSession, user_id: int, author_id: int) -> AuthorFollow | None:
    return await session.scalar(
        select(AuthorFollow).where(
            AuthorFollow.user_id == user_id,
            AuthorFollow.author_id == author_id,
        )
    )


async def follow_author(
    session: AsyncSession,
    user_id: int,
    author_id: int,
    *,
    weight: float = 1.0,
    notify: bool = False,
) -> AuthorFollow:
    follow = await get_follow(session, user_id, author_id)
    if follow is None:
        follow = AuthorFollow(
            user_id=user_id, author_id=author_id, weight=weight, notify=notify
        )
        session.add(follow)
    else:
        follow.weight = weight
        follow.notify = notify
    await session.commit()
    await session.refresh(follow)
    return follow


async def unfollow_author(session: AsyncSession, user_id: int, author_id: int) -> bool:
    result = await session.execute(
        delete(AuthorFollow).where(
            AuthorFollow.user_id == user_id,
            AuthorFollow.author_id == author_id,
        )
    )
    await session.commit()
    return (result.rowcount or 0) > 0


async def followed_author_ids(session: AsyncSession, user_id: int) -> set[int]:
    rows = await session.scalars(
        select(AuthorFollow.author_id).where(AuthorFollow.user_id == user_id)
    )
    return set(rows.all())


async def author_weight_map(session: AsyncSession, user_id: int) -> dict[int, float]:
    rows = await session.execute(
        select(AuthorFollow.author_id, AuthorFollow.weight).where(
            AuthorFollow.user_id == user_id
        )
    )
    return {author_id: weight for author_id, weight in rows.all()}
