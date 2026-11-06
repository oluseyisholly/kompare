from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


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
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "interval_minutes": 60,
                    "is_enabled": False,
                    "next_run_at": None,
                    "notes": "Hourly refresh; enable when ready to schedule ingestion.",
                }
            ]
        }
    )

    interval_minutes: int = Field(..., ge=1)
    is_enabled: bool = True
    next_run_at: datetime | None = None
    notes: str | None = None
