from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class IngestionScheduleRead(BaseModel):
    id: int
    provider_id: int
    provider_slug: str
    job_type: str
    interval_minutes: int
    is_enabled: bool
    next_run_at: datetime | None = None
    last_run_at: datetime | None = None
    notes: str | None = None
    metadata_json: dict | None = None
    created_at: datetime
    updated_at: datetime


class IngestionScheduleUpsert(BaseModel):
    interval_minutes: int = Field(..., ge=1)
    is_enabled: bool = True
    next_run_at: datetime | None = None
    notes: str | None = None
