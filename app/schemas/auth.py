from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import AdminType


class UserRead(BaseModel):
    id: int
    email: str = Field(
        min_length=3,
        max_length=254,
        pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$",
        examples=["user@example.com"],
    )
    first_name: str | None = None
    last_name: str | None = None
    phone_number: str | None = None
    role: str
    admin_type: AdminType | None = None
    status: str
    is_superadmin: bool
    is_active: bool
    is_verified: bool
    is_phone_verified: bool
    last_login_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class AuthenticatedUser(BaseModel):
    id: int
    email: str = Field(
        min_length=3,
        max_length=254,
        pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$",
        examples=["user@example.com"],
    )
    first_name: str | None = None
    last_name: str | None = None
    phone_number: str | None = None
    role: str
    admin_type: AdminType | None = None
    status: str
    is_superadmin: bool
    is_active: bool
    is_verified: bool
    is_phone_verified: bool
    last_login_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class UserRegisterRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "email": "user@example.com",
                    "password": "ExamplePassword123!",
                    "first_name": "Ada",
                    "last_name": "Okafor",
                    "phone_number": None,
                }
            ]
        }
    )

    email: str = Field(
        min_length=3,
        max_length=254,
        pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$",
        examples=["user@example.com"],
    )
    password: str = Field(min_length=8, max_length=128)
    first_name: str | None = None
    last_name: str | None = None
    phone_number: str | None = None


class AdminRegisterRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "email": "admin@example.com",
                    "password": "ExamplePassword123!",
                    "first_name": "Ada",
                    "last_name": "Okafor",
                    "admin_type": AdminType.SUPPORT_ADMIN.value,
                }
            ]
        }
    )

    email: str = Field(
        min_length=3,
        max_length=254,
        pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$",
        examples=["user@example.com"],
    )
    password: str = Field(min_length=8, max_length=128)
    first_name: str | None = None
    last_name: str | None = None
    admin_type: AdminType = AdminType.SUPPORT_ADMIN


class LoginRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "email": "user@example.com",
                    "password": "ExamplePassword123!",
                }
            ]
        }
    )

    email: str = Field(
        min_length=3,
        max_length=254,
        pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$",
        examples=["user@example.com"],
    )
    password: str = Field(min_length=8, max_length=128)


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserRead


class RefreshTokenRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "refresh_token": "paste-your-refresh-token-from-login",
                }
            ]
        }
    )

    refresh_token: str = Field(
        description="Use the real refresh_token returned by login or refresh."
    )


class VerifyEmailRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "email": "user@example.com",
                    "otp": "123456",
                }
            ]
        }
    )

    email: str = Field(
        min_length=3,
        max_length=254,
        pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$",
        examples=["user@example.com"],
    )
    otp: str = Field(
        min_length=4,
        max_length=12,
        examples=["123456"],
        description="Replace with the verification code sent to your email.",
    )


class ResendEmailVerificationOtpRequest(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [{"email": "user@example.com"}]})

    email: str = Field(
        min_length=3,
        max_length=254,
        pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$",
        examples=["user@example.com"],
    )


class ForgotPasswordRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid", json_schema_extra={"examples": [{"email": "user@example.com"}]}
    )

    email: str = Field(
        min_length=3,
        max_length=254,
        pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$",
        examples=["user@example.com"],
    )


class ResetPasswordRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "email": "user@example.com",
                    "otp": "123456",
                    "new_password": "NewExamplePassword123!",
                }
            ]
        },
    )

    email: str = Field(
        min_length=3,
        max_length=254,
        pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$",
        examples=["user@example.com"],
    )
    otp: str = Field(
        min_length=6,
        max_length=12,
        pattern=r"^[0-9]+$",
        examples=["123456"],
        description="Use the password reset code sent to your email. "
        "Email verification codes cannot reset passwords.",
    )
    new_password: str = Field(min_length=8, max_length=128)
