from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class UserRead(BaseModel):
    id: int
    email: str
    first_name: str | None = None
    last_name: str | None = None
    role: str
    is_superadmin: bool
    is_active: bool
    is_verified: bool
    last_login_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class UserRegisterRequest(BaseModel):
    email: str
    password: str = Field(min_length=8)
    first_name: str | None = None
    last_name: str | None = None


class AdminRegisterRequest(BaseModel):
    email: str
    password: str = Field(min_length=8)
    first_name: str | None = None
    last_name: str | None = None


class LoginRequest(BaseModel):
    email: str
    password: str = Field(min_length=8)


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserRead
