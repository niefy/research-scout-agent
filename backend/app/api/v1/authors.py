from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, status
from sqlalchemy import func, or_, select

from app.api.deps import DB, CurrentUser
from app.models.author import Author, AuthorIdentity
from app.models.personalization import AuthorFollow
from app.schemas.author import (
    AuthorCreate,
    AuthorDetail,
    AuthorFollowIn,
    AuthorFollowOut,
    AuthorImportIn,
    AuthorImportOut,
    AuthorOut,
    AuthorUpdate,
    RecommendedAuthorOut,
)
from app.schemas.common import Message, Page
from app.services import authors as author_service
from app.services.author_crawl import backfill_author

router = APIRouter(prefix="/authors", tags=["authors"])


@router.get("", response_model=Page[AuthorOut])
async def list_authors(
    session: DB,
    user: CurrentUser,
    q: str | None = Query(default=None, max_length=64),
    followed: bool = False,
    curated: bool = False,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> Page[AuthorOut]:
    stmt = select(Author)
    count_stmt = select(func.count(Author.id))
    if followed:
        stmt = stmt.join(AuthorFollow, AuthorFollow.author_id == Author.id).where(
            AuthorFollow.user_id == user.id
        )
        count_stmt = count_stmt.join(AuthorFollow, AuthorFollow.author_id == Author.id).where(
            AuthorFollow.user_id == user.id
        )
    if curated:
        stmt = stmt.where(Author.is_curated.is_(True))
        count_stmt = count_stmt.where(Author.is_curated.is_(True))
    if q:
        pattern = f"%{q.strip()}%"
        condition = or_(Author.canonical_name.ilike(pattern), Author.normalized_name.ilike(pattern))
        stmt = stmt.where(condition)
        count_stmt = count_stmt.where(condition)

    total = await session.scalar(count_stmt) or 0
    rows = (
        await session.scalars(
            stmt.order_by(Author.canonical_name)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    return Page[AuthorOut](
        items=[AuthorOut.model_validate(row) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
        has_more=page * page_size < total,
    )


@router.get("/following", response_model=list[AuthorFollowOut])
async def list_following(session: DB, user: CurrentUser) -> list[AuthorFollowOut]:
    rows = (
        await session.execute(
            select(AuthorFollow, Author)
            .join(Author, AuthorFollow.author_id == Author.id)
            .where(AuthorFollow.user_id == user.id)
            .order_by(AuthorFollow.created_at.desc())
        )
    ).all()
    return [
        AuthorFollowOut(
            author=AuthorOut.model_validate(author),
            weight=follow.weight,
            notify=follow.notify,
            followed_at=follow.created_at,
        )
        for follow, author in rows
    ]


@router.get("/recommended", response_model=list[RecommendedAuthorOut])
async def recommended_authors(
    session: DB,
    user: CurrentUser,
    limit: int = Query(default=10, ge=1, le=50),
) -> list[RecommendedAuthorOut]:
    rows = await author_service.recommended_authors(session, user.id, limit=limit)
    return [RecommendedAuthorOut(**row) for row in rows]


@router.post("/import", response_model=AuthorImportOut, status_code=status.HTTP_201_CREATED)
async def import_author(
    payload: AuthorImportIn,
    session: DB,
    user: CurrentUser,
    background_tasks: BackgroundTasks,
) -> AuthorImportOut:
    if not payload.external_id and not payload.profile_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="external_id or profile_url is required",
        )
    try:
        author, follow, created, newly_followed = await author_service.import_xueqiu_author(
            session,
            user_id=user.id,
            external_id=payload.external_id,
            profile_url=payload.profile_url,
            display_name=payload.display_name,
            follow=payload.follow,
            weight=payload.weight,
        )
    except author_service.AuthorImportError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    backfill_scheduled = bool(payload.follow and newly_followed and follow is not None)
    if backfill_scheduled:
        background_tasks.add_task(backfill_author, author.id)
    return AuthorImportOut(
        author=AuthorOut.model_validate(author),
        followed=follow is not None,
        created=created,
        backfill_scheduled=backfill_scheduled,
    )


@router.post("", response_model=AuthorDetail, status_code=status.HTTP_201_CREATED)
async def create_author(payload: AuthorCreate, session: DB, user: CurrentUser) -> AuthorDetail:
    try:
        author = await author_service.create_author(session, payload, user.id)
    except author_service.AuthorConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    detail = await author_service.author_detail(session, author.id)
    return AuthorDetail.model_validate(detail)


@router.get("/{author_id}", response_model=AuthorDetail)
async def get_author(author_id: int, session: DB, user: CurrentUser) -> AuthorDetail:
    detail = await author_service.author_detail(session, author_id)
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="author not found")
    return AuthorDetail.model_validate(detail)


@router.patch("/{author_id}", response_model=AuthorOut)
async def update_author(
    author_id: int,
    payload: AuthorUpdate,
    session: DB,
    user: CurrentUser,
) -> AuthorOut:
    author = await session.get(Author, author_id)
    if author is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="author not found")
    if user.role != "admin" and author.created_by_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="only the creator or an admin can edit this author",
        )
    if payload.canonical_name is not None:
        from app.services.authors import normalize_author_name

        normalized = normalize_author_name(payload.canonical_name)
        conflict = await session.scalar(
            select(Author).where(Author.normalized_name == normalized, Author.id != author.id)
        )
        if conflict is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="another author already uses this name",
            )
        author.canonical_name = payload.canonical_name.strip()
        author.normalized_name = normalized
    if payload.author_type is not None:
        author.author_type = payload.author_type
    if payload.default_weight is not None:
        author.default_weight = payload.default_weight
    if payload.status is not None:
        author.status = payload.status
    await session.commit()
    await session.refresh(author)
    return AuthorOut.model_validate(author)


@router.post("/{author_id}/follow", response_model=AuthorFollowOut)
async def follow_author(
    author_id: int,
    payload: AuthorFollowIn,
    session: DB,
    user: CurrentUser,
    background_tasks: BackgroundTasks,
) -> AuthorFollowOut:
    author = await session.get(Author, author_id)
    if author is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="author not found")
    existing = await author_service.get_follow(session, user.id, author_id)
    follow = await author_service.follow_author(
        session,
        user.id,
        author_id,
        weight=payload.weight,
        notify=payload.notify,
    )
    if existing is None and author.crawl_enabled:
        has_identity = await session.scalar(
            select(AuthorIdentity.id).where(AuthorIdentity.author_id == author_id).limit(1)
        )
        if has_identity is not None:
            background_tasks.add_task(backfill_author, author_id)
    return AuthorFollowOut(
        author=AuthorOut.model_validate(author),
        weight=follow.weight,
        notify=follow.notify,
        followed_at=follow.created_at,
    )


@router.delete("/{author_id}/follow", response_model=Message)
async def unfollow_author(author_id: int, session: DB, user: CurrentUser) -> Message:
    removed = await author_service.unfollow_author(session, user.id, author_id)
    if not removed:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not following")
    return Message(message="unfollowed")
