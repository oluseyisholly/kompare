from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import (
    ProviderReviewStatus,
    ProviderReviewTag,
    ProviderReviewType,
    ProviderTipCategory,
    ProviderTipSeverity,
)


class EnumOptionRead(BaseModel):
    label: str
    value: str


class ReviewUserRead(BaseModel):
    id: int | None = None
    first_name: str | None = None
    last_name: str | None = None
    is_anonymous: bool = False


class ProviderReviewCreate(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "rating": 4,
                    "title": "Easy to use",
                    "body": "The application was easy to navigate.",
                    "tags": ["ease_of_use"],
                }
            ]
        }
    )

    rating: int = Field(ge=1, le=5)
    title: str = Field(min_length=1, max_length=255)
    body: str = Field(min_length=1)
    tags: list[ProviderReviewTag] = Field(default_factory=list)


class ProviderTipCreate(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "tip_category": "general_tip",
                    "body": "Check the displayed rate and fees before confirming a transfer.",
                }
            ]
        }
    )

    tip_category: ProviderTipCategory
    body: str = Field(min_length=1)


class ProviderReviewUpdate(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "rating": 5,
                    "title": "Helpful support",
                    "body": "Support resolved my issue.",
                    "tags": ["support_quality"],
                }
            ]
        }
    )

    rating: int | None = Field(default=None, ge=1, le=5)
    title: str | None = Field(default=None, min_length=1, max_length=255)
    body: str | None = Field(default=None, min_length=1)
    tags: list[ProviderReviewTag] | None = None


class ProviderReviewStatusUpdate(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{"status": "published", "note": "Reviewed and approved for publication."}]
        }
    )

    status: ProviderReviewStatus
    note: str | None = None


class ProviderReviewVoteUpsert(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [{"is_helpful": True}]})

    is_helpful: bool


class ProviderReviewVoteSummary(BaseModel):
    review_id: int
    helpful_count: int
    not_helpful_count: int


class ProviderReviewSummary(BaseModel):
    provider_slug: str
    average_rating: float | None
    total_reviews: int
    rating_counts: dict[str, int]


class ProviderReviewRead(BaseModel):
    id: int
    provider_id: int
    provider_slug: str
    user: ReviewUserRead
    review_type: ProviderReviewType
    tip_category: ProviderTipCategory | None
    tip_severity: ProviderTipSeverity | None
    rating: int | None
    title: str | None
    body: str
    tags: list[str]
    status: str
    is_verified: bool
    reviewed_at: datetime
    helpful_count: int
    not_helpful_count: int
    comments_count: int
    created_at: datetime
    updated_at: datetime


class ProviderReviewCommentCreate(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={"examples": [{"body": "Thanks for sharing your experience."}]}
    )

    body: str = Field(min_length=1)


class ProviderReviewCommentRead(BaseModel):
    id: int
    review_id: int
    user: ReviewUserRead
    body: str
    status: str
    created_at: datetime
    updated_at: datetime
