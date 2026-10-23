from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.schemas.common import ORMModel


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    nickname: str = Field(min_length=1, max_length=64)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class UserOut(ORMModel):
    id: int
    email: EmailStr | None = None
    phone: str | None = None
    nickname: str
    role: str
    status: str
    scoring_config: dict = Field(default_factory=dict)
    digest_email_enabled: bool = False
    created_at: datetime


class UserUpdate(BaseModel):
    nickname: str | None = Field(default=None, min_length=1, max_length=64)
    scoring_config: dict | None = None
    digest_email_enabled: bool | None = None


class PasswordChange(BaseModel):
    old_password: str
    new_password: str = Field(min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def _new_password_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("password must not be blank")
        return value
