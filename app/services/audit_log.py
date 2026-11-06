from __future__ import annotations

from typing import Any

from app.models.audit_log import AuditLog
from app.repositories.audit_log import AuditLogRepository
from app.schemas.audit_log import AuditActorRead, AuditLogEntityTypeOption, AuditLogRead
from app.schemas.common import ApiResponse, PaginatedData, build_paginated_response

AUDIT_LOG_ENTITY_TYPE_OPTIONS = [
    ("All entities", "all"),
    ("System", "system"),
    ("User", "user"),
    ("DeletionRequest", "deletion_request"),
    ("Tip", "tip"),
    ("Provider", "provider"),
    ("FieldSuggestion", "field_suggestion"),
    ("Review", "provider_review"),
    ("DataSource", "data_source"),
]


class AuditLogService:
    def __init__(self, repository: AuditLogRepository) -> None:
        self.repository = repository

    def record(
        self,
        *,
        action: str,
        entity_type: str,
        entity_id: int | str | None = None,
        actor_user_id: int | None = None,
        old_values: dict[str, Any] | None = None,
        new_values: dict[str, Any] | None = None,
        metadata_json: dict[str, Any] | None = None,
        note: str | None = None,
    ) -> AuditLog:
        return self.repository.create(
            AuditLog(
                actor_user_id=actor_user_id,
                action=action,
                entity_type=entity_type,
                entity_id=str(entity_id) if entity_id is not None else None,
                old_values=old_values,
                new_values=new_values,
                metadata_json=metadata_json,
                note=note,
            )
        )

    @staticmethod
    def _actor_to_schema(actor_user) -> AuditActorRead:
        if actor_user is None:
            return AuditActorRead(id=None, type="system", name="System", email=None)

        full_name = " ".join(
            part for part in [actor_user.first_name, actor_user.last_name] if part
        ).strip()
        return AuditActorRead(
            id=actor_user.id,
            type="user",
            name=full_name or actor_user.email,
            email=actor_user.email,
        )

    def _to_schema(self, audit_log: AuditLog) -> AuditLogRead:
        return AuditLogRead(
            id=audit_log.id,
            actor_user_id=audit_log.actor_user_id,
            actor=self._actor_to_schema(audit_log.actor_user),
            action=audit_log.action,
            entity_type=audit_log.entity_type,
            entity_id=audit_log.entity_id,
            old_values=audit_log.old_values,
            new_values=audit_log.new_values,
            metadata_json=audit_log.metadata_json,
            note=audit_log.note,
            reason=audit_log.note,
            created_at=audit_log.created_at,
        )

    def list(
        self,
        *,
        page: int,
        per_page: int,
        entity_type: str | None = None,
        entity_id: str | None = None,
        actor_user_id: int | None = None,
        action: str | None = None,
        search: str | None = None,
    ) -> ApiResponse[PaginatedData[AuditLogRead]]:
        entity_filter = None if entity_type in (None, "", "all") else entity_type
        rows, total = self.repository.list(
            page=page,
            per_page=per_page,
            entity_type=entity_filter,
            entity_id=entity_id,
            actor_user_id=actor_user_id,
            action=action,
            search=search,
        )
        return build_paginated_response(
            items=[self._to_schema(row) for row in rows],
            page=page,
            per_page=per_page,
            total=total,
            message="Audit logs retrieved successfully",
        )

    def list_entity_type_options(self) -> ApiResponse[list[AuditLogEntityTypeOption]]:
        return ApiResponse(
            responseCode=200,
            message="Audit log entity type options retrieved successfully",
            data=[
                AuditLogEntityTypeOption(label=label, value=value)
                for label, value in AUDIT_LOG_ENTITY_TYPE_OPTIONS
            ],
        )
