from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ProviderRead(BaseModel):
    id: int
    slug: str
    name: str
    description: str | None = None
    logo_url: str | None = None
    website_url: str | None = None
    category: str
    is_active: bool
    has_adapter: bool
    metadata_json: dict | None = None
    created_at: datetime
    updated_at: datetime


class ProviderUpdate(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "description": "Updated provider description.",
                }
            ]
        }
    )

    name: str | None = None
    description: str | None = None
    logo_url: str | None = None
    website_url: str | None = None
    is_active: bool | None = None
    has_adapter: bool | None = None
    metadata_json: dict | None = None


class ProviderOverviewRead(BaseModel):
    id: int
    slug: str
    name: str
    description: str | None = None
    logo_url: str | None = None
    website_url: str | None = None
    category: str
    status: str
    is_active: bool
    has_adapter: bool
    average_rating: float | None = None
    review_count: int
    data_source: str
    feed_health: str
    coverage_score: int
    coverage_label: str
    sync_mode: str
    last_synced_at: datetime | None = None
