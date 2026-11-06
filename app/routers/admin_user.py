from fastapi import APIRouter, Depends, Query

from app.dependencies.auth import get_current_user, require_admin
from app.dependencies.providers import get_admin_user_service
from app.schemas.admin_user import (
    AdminUserDetailRead,
    AdminUserRead,
    UserDeletionRequestCreate,
    UserDeletionRequestRead,
    UserDeletionRequestStatusUpdate,
    UserStatusOptionRead,
    UserSuspendRequest,
)
from app.schemas.auth import AuthenticatedUser
from app.schemas.common import ApiResponse, PaginatedData
from app.schemas.provider_review import ProviderReviewRead
from app.services.admin_user import AdminUserService

router = APIRouter(tags=["admin-users"])


@router.get("/admin/users/statuses", response_model=ApiResponse[list[UserStatusOptionRead]])
def list_user_statuses(
    service: AdminUserService = Depends(get_admin_user_service),
    current_user: AuthenticatedUser = Depends(require_admin),
) -> ApiResponse[list[UserStatusOptionRead]]:
    del current_user
    return service.list_user_status_options()


@router.get("/admin/users", response_model=ApiResponse[PaginatedData[AdminUserRead]])
def list_users(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    search: str | None = Query(default=None),
    status: str | None = Query(default=None),
    service: AdminUserService = Depends(get_admin_user_service),
    current_user: AuthenticatedUser = Depends(require_admin),
) -> ApiResponse[PaginatedData[AdminUserRead]]:
    del current_user
    return service.list_users(page=page, per_page=per_page, search=search, status=status)


@router.get(
    "/admin/users/deletion-requests",
    response_model=ApiResponse[PaginatedData[UserDeletionRequestRead]],
)
def list_deletion_requests(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    search: str | None = Query(default=None),
    status: str | None = Query(default=None),
    service: AdminUserService = Depends(get_admin_user_service),
    current_user: AuthenticatedUser = Depends(require_admin),
) -> ApiResponse[PaginatedData[UserDeletionRequestRead]]:
    del current_user
    return service.list_deletion_requests(
        page=page, per_page=per_page, search=search, status=status
    )


@router.patch(
    "/admin/users/deletion-requests/{request_id}/start-processing",
    response_model=ApiResponse[UserDeletionRequestRead],
)
def start_processing_deletion_request(
    request_id: int,
    payload: UserDeletionRequestStatusUpdate,
    service: AdminUserService = Depends(get_admin_user_service),
    current_user: AuthenticatedUser = Depends(require_admin),
) -> ApiResponse[UserDeletionRequestRead]:
    return service.start_processing_deletion_request(
        request_id, payload=payload, current_user=current_user
    )


@router.patch(
    "/admin/users/deletion-requests/{request_id}/complete",
    response_model=ApiResponse[UserDeletionRequestRead],
)
def complete_deletion_request(
    request_id: int,
    payload: UserDeletionRequestStatusUpdate,
    service: AdminUserService = Depends(get_admin_user_service),
    current_user: AuthenticatedUser = Depends(require_admin),
) -> ApiResponse[UserDeletionRequestRead]:
    return service.complete_deletion_request(request_id, payload=payload, current_user=current_user)


@router.patch(
    "/admin/users/deletion-requests/{request_id}/cancel",
    response_model=ApiResponse[UserDeletionRequestRead],
)
def cancel_deletion_request(
    request_id: int,
    payload: UserDeletionRequestStatusUpdate,
    service: AdminUserService = Depends(get_admin_user_service),
    current_user: AuthenticatedUser = Depends(require_admin),
) -> ApiResponse[UserDeletionRequestRead]:
    return service.cancel_deletion_request(request_id, payload=payload, current_user=current_user)


@router.get("/admin/users/{user_id}", response_model=ApiResponse[AdminUserDetailRead])
def get_user(
    user_id: int,
    service: AdminUserService = Depends(get_admin_user_service),
    current_user: AuthenticatedUser = Depends(require_admin),
) -> ApiResponse[AdminUserDetailRead]:
    del current_user
    return service.get_user_detail(user_id)


@router.get(
    "/admin/users/{user_id}/reviews", response_model=ApiResponse[PaginatedData[ProviderReviewRead]]
)
def list_user_reviews(
    user_id: int,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    service: AdminUserService = Depends(get_admin_user_service),
    current_user: AuthenticatedUser = Depends(require_admin),
) -> ApiResponse[PaginatedData[ProviderReviewRead]]:
    del current_user
    return service.list_user_reviews(user_id, page=page, per_page=per_page)


@router.post("/admin/users/{user_id}/resend-verification", response_model=ApiResponse[dict])
def resend_user_verification(
    user_id: int,
    service: AdminUserService = Depends(get_admin_user_service),
    current_user: AuthenticatedUser = Depends(require_admin),
) -> ApiResponse[dict]:
    return service.resend_verification(user_id, current_user=current_user)


@router.patch("/admin/users/{user_id}/suspend", response_model=ApiResponse[AdminUserRead])
def suspend_user(
    user_id: int,
    payload: UserSuspendRequest,
    service: AdminUserService = Depends(get_admin_user_service),
    current_user: AuthenticatedUser = Depends(require_admin),
) -> ApiResponse[AdminUserRead]:
    return service.suspend_user(user_id, reason=payload.reason, current_user=current_user)


@router.patch("/admin/users/{user_id}/activate", response_model=ApiResponse[AdminUserRead])
def activate_user(
    user_id: int,
    service: AdminUserService = Depends(get_admin_user_service),
    current_user: AuthenticatedUser = Depends(require_admin),
) -> ApiResponse[AdminUserRead]:
    return service.activate_user(user_id, current_user=current_user)


@router.post(
    "/users/me/deletion-request",
    response_model=ApiResponse[UserDeletionRequestRead],
    status_code=201,
)
def create_my_deletion_request(
    payload: UserDeletionRequestCreate,
    service: AdminUserService = Depends(get_admin_user_service),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> ApiResponse[UserDeletionRequestRead]:
    return service.create_my_deletion_request(payload, current_user)
