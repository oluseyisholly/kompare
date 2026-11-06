from __future__ import annotations

from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.models.audit_log import AuditLog
from app.repositories.pagination import paginate_query


class AuditLogRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, audit_log: AuditLog) -> AuditLog:
        self.db.add(audit_log)
        self.db.commit()
        self.db.refresh(audit_log)
        return audit_log

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
    ) -> tuple[list[AuditLog], int]:
        query = (
            self.db.query(AuditLog)
            .options(joinedload(AuditLog.actor_user))
            .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        )
        if entity_type is not None:
            query = query.filter(AuditLog.entity_type == entity_type)
        if entity_id is not None:
            query = query.filter(AuditLog.entity_id == entity_id)
        if actor_user_id is not None:
            query = query.filter(AuditLog.actor_user_id == actor_user_id)
        if action is not None:
            query = query.filter(AuditLog.action == action)
        if search:
            search_value = f"%{search.strip()}%"
            query = query.filter(
                or_(
                    AuditLog.action.ilike(search_value),
                    AuditLog.entity_type.ilike(search_value),
                    AuditLog.entity_id.ilike(search_value),
                    AuditLog.note.ilike(search_value),
                )
            )
        return paginate_query(query, page=page, per_page=per_page)
