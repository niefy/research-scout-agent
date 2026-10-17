from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import (
    TokenError,
    create_token_pair,
    hash_password,
    user_id_from_token,
    verify_password,
)
from app.models.user import User


class AuthError(ValueError):
    pass


class EmailAlreadyExists(AuthError):
    pass


def _tokens(user: User) -> dict:
    access, refresh = create_token_pair(user.id)
    return {
        "access_token": access,
        "refresh_token": refresh,
        "token_type": "bearer",
        "expires_in": settings.access_token_ttl_minutes * 60,
    }


async def register_user(
    session: AsyncSession,
    *,
    email: str,
    password: str,
    nickname: str,
) -> tuple[User, dict]:
    normalized_email = email.strip().lower()
    existing = await session.scalar(select(User).where(User.email == normalized_email))
    if existing is not None:
        raise EmailAlreadyExists("email already registered")

    user = User(
        email=normalized_email,
        password_hash=hash_password(password),
        nickname=nickname.strip(),
        role="user",
        status="active",
        scoring_config={},
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user, _tokens(user)


async def authenticate(session: AsyncSession, *, email: str, password: str) -> tuple[User, dict]:
    normalized_email = email.strip().lower()
    user = await session.scalar(
        select(User).where(or_(User.email == normalized_email, User.phone == email.strip()))
    )
    if user is None or not verify_password(password, user.password_hash):
        raise AuthError("invalid email or password")
    if user.status != "active":
        raise AuthError("account is disabled")
    return user, _tokens(user)


async def refresh_session(session: AsyncSession, refresh_token: str) -> dict:
    try:
        user_id = user_id_from_token(refresh_token, expected_type="refresh")
    except TokenError as exc:
        raise AuthError("invalid refresh token") from exc
    user = await session.get(User, user_id)
    if user is None or user.status != "active":
        raise AuthError("user not found or disabled")
    return _tokens(user)


async def update_profile(
    session: AsyncSession,
    user: User,
    *,
    nickname: str | None = None,
    scoring_config: dict | None = None,
) -> User:
    if nickname is not None:
        user.nickname = nickname.strip()
    if scoring_config is not None:
        user.scoring_config = scoring_config
    await session.commit()
    await session.refresh(user)
    return user


async def change_password(
    session: AsyncSession,
    user: User,
    *,
    old_password: str,
    new_password: str,
) -> None:
    if not verify_password(old_password, user.password_hash):
        raise AuthError("old password is incorrect")
    user.password_hash = hash_password(new_password)
    await session.commit()


def decode_access_token(token: str) -> int:
    return user_id_from_token(token, expected_type="access")


__all__ = [
    "AuthError",
    "EmailAlreadyExists",
    "authenticate",
    "change_password",
    "decode_access_token",
    "refresh_session",
    "register_user",
    "update_profile",
]
