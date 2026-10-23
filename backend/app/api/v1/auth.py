from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.api.deps import DB, CurrentUser
from app.schemas.auth import (
    LoginRequest,
    PasswordChange,
    RefreshRequest,
    RegisterRequest,
    TokenPair,
    UserOut,
    UserUpdate,
)
from app.schemas.common import Message
from app.services import auth as auth_service

router = APIRouter(tags=["auth"])


@router.post("/auth/register", response_model=TokenPair, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest, session: DB) -> TokenPair:
    try:
        _, tokens = await auth_service.register_user(
            session,
            email=payload.email,
            password=payload.password,
            nickname=payload.nickname,
        )
    except auth_service.EmailAlreadyExists as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return TokenPair(**tokens)


@router.post("/auth/login", response_model=TokenPair)
async def login(payload: LoginRequest, session: DB) -> TokenPair:
    try:
        _, tokens = await auth_service.authenticate(
            session, email=payload.email, password=payload.password
        )
    except auth_service.AuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    return TokenPair(**tokens)


@router.post("/auth/refresh", response_model=TokenPair)
async def refresh(payload: RefreshRequest, session: DB) -> TokenPair:
    try:
        tokens = await auth_service.refresh_session(session, payload.refresh_token)
    except auth_service.AuthError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    return TokenPair(**tokens)


@router.get("/users/me", response_model=UserOut)
async def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)


@router.patch("/users/me", response_model=UserOut)
async def update_me(payload: UserUpdate, user: CurrentUser, session: DB) -> UserOut:
    updated = await auth_service.update_profile(
        session,
        user,
        nickname=payload.nickname,
        scoring_config=payload.scoring_config,
        digest_email_enabled=payload.digest_email_enabled,
    )
    return UserOut.model_validate(updated)


@router.post("/users/me/password", response_model=Message)
async def change_password(
    payload: PasswordChange,
    user: CurrentUser,
    session: DB,
) -> Message:
    try:
        await auth_service.change_password(
            session,
            user,
            old_password=payload.old_password,
            new_password=payload.new_password,
        )
    except auth_service.AuthError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return Message(message="password updated")
