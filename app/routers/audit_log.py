from fastapi import APIRouter, Depends, Query

from app.dependencies.auth import require_admin
from app.dependencies.providers import get_audit_log_service
from app.schemas.audit_log import AuditLogEntityTypeOption, AuditLogRead
from app.schemas.auth import AuthenticatedUser
from app.schemas.common import ApiResponse, PaginatedData
from app.services.audit_log import AuditLogService

router = APIRouter(prefix="/admin/audit-logs", tags=["admin"])


@router.get("/entity-types", response_model=ApiResponse[list[AuditLogEntityTypeOption]])
def list_audit_log_entity_types(
    service: AuditLogService = Depends(get_audit_log_service),
    current_user: AuthenticatedUser = Depends(require_admin),
) -> ApiResponse[list[AuditLogEntityTypeOption]]:
    del current_user
    return service.list_entity_type_options()


@router.get("/", response_model=ApiResponse[PaginatedData[AuditLogRead]])
def list_audit_logs(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    entity_type: str | None = Query(default=None),
    entity_id: str | None = Query(default=None),
    actor_user_id: int | None = Query(default=None, ge=1),
    action: str | None = Query(default=None),
    search: str | None = Query(default=None),
    service: AuditLogService = Depends(get_audit_log_service),
    current_user: AuthenticatedUser = Depends(require_admin),
) -> ApiResponse[PaginatedData[AuditLogRead]]:
    del current_user
    return service.list(
        page=page,
        per_page=per_page,
        entity_type=entity_type,
        entity_id=entity_id,
        actor_user_id=actor_user_id,
        action=action,
        search=search,
    )
