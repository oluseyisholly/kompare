from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import UserDeletionRequestStatus
from app.schemas.provider_review import ProviderReviewRead


class AdminUserRead(BaseModel):
    id: int
    email: str = Field(examples=["user@example.com"])
    first_name: str | None = None
    last_name: str | None = None
    name: str
    phone_number: str | None = None
    role: str
    admin_type: str | None = None
    status: str
    is_active: bool
    is_verified: bool
    is_phone_verified: bool
    reviews_count: int
    last_active_at: datetime | None = None
    joined_at: datetime
    suspended_at: datetime | None = None
    suspended_reason: str | None = None


class AdminUserDetailRead(AdminUserRead):
    reviews: list[ProviderReviewRead] = Field(default_factory=list)


class UserSuspendRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={"examples": [{"reason": "Account suspended pending review."}]}
    )

    reason: str | None = None


class UserDeletionRequestCreate(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={"examples": [{"reason": "I no longer need my account."}]}
    )

    reason: str | None = None


class UserDeletionRequestStatusUpdate(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={"examples": [{"note": "Account deletion request reviewed by support."}]}
    )

    note: str | None = None


class UserDeletionRequestUserRead(BaseModel):
    id: int
    email: str = Field(examples=["user@example.com"])
    first_name: str | None = None
    last_name: str | None = None
    name: str


class UserDeletionRequestRead(BaseModel):
    id: int
    user: UserDeletionRequestUserRead
    status: UserDeletionRequestStatus
    reason: str | None = None
    requested_at: datetime
    grace_ends_at: datetime | None = None
    processing_started_at: datetime | None = None
    completed_at: datetime | None = None
    cancelled_at: datetime | None = None
    processed_by_user_id: int | None = None
    admin_note: str | None = None
    created_at: datetime
    updated_at: datetime


class UserStatusOptionRead(BaseModel):
    label: str
    value: str
