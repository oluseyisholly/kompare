from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class AuditActorRead(BaseModel):
    id: int | None
    type: str
    name: str
    email: str | None = Field(default=None, examples=["user@example.com"])


class AuditLogRead(BaseModel):
    id: int
    actor_user_id: int | None
    actor: AuditActorRead
    action: str
    entity_type: str
    entity_id: str | None
    old_values: dict[str, Any] | None
    new_values: dict[str, Any] | None
    metadata_json: dict[str, Any] | None
    note: str | None
    reason: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class AuditLogEntityTypeOption(BaseModel):
    label: str
    value: str
