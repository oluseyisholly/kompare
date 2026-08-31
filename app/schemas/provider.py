from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


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
    name: str | None = None
    description: str | None = None
    logo_url: str | None = None
    website_url: str | None = None
    is_active: bool | None = None
    has_adapter: bool | None = None
    metadata_json: dict | None = None
