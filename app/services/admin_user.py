from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.core.exceptions import BadRequestError, NotFoundError
from app.models.enums import UserDeletionRequestStatus, UserRole, UserStatus
from app.models.user_deletion_request import UserDeletionRequest
from app.repositories.user import UserRepository
from app.repositories.user_deletion_request import UserDeletionRequestRepository
from app.schemas.admin_user import (
    AdminUserDetailRead,
    AdminUserRead,
    UserDeletionRequestCreate,
    UserDeletionRequestRead,
    UserDeletionRequestStatusUpdate,
    UserDeletionRequestUserRead,
    UserStatusOptionRead,
)
from app.schemas.auth import AuthenticatedUser
from app.schemas.common import ApiResponse, PaginatedData, build_paginated_response
from app.services.audit_log import AuditLogService
from app.services.auth import AuthService
from app.services.provider_review import ProviderReviewService

USER_DELETION_GRACE_DAYS = 14


class AdminUserService:
    def __init__(
        self,
        *,
        user_repository: UserRepository,
        deletion_request_repository: UserDeletionRequestRepository,
        auth_service: AuthService,
        audit_log_service: AuditLogService,
        provider_review_service: ProviderReviewService,
    ) -> None:
        self.user_repository = user_repository
        self.deletion_request_repository = deletion_request_repository
        self.auth_service = auth_service
        self.audit_log_service = audit_log_service
        self.provider_review_service = provider_review_service

    def list_users(
        self,
        *,
        page: int,
        per_page: int,
        search: str | None = None,
        status: str | None = None,
    ) -> ApiResponse[PaginatedData[AdminUserRead]]:
        status_enum = self._parse_user_status(status)
        rows, total = self.user_repository.list_for_admin(
            page=page,
            per_page=per_page,
            search=search,
            status=status_enum,
        )
        return build_paginated_response(
            items=[
                self._user_to_schema(user, reviews_count=int(reviews_count or 0))
                for user, reviews_count in rows
            ],
            page=page,
            per_page=per_page,
            total=total,
            message="Users retrieved successfully",
        )

    def get_user_detail(self, user_id: int) -> ApiResponse[AdminUserDetailRead]:
        user = self._get_user_or_raise(user_id)
        reviews, _ = self.user_repository.list_reviews(user.id, page=1, per_page=10)
        base = self._user_to_schema(user, reviews_count=self.user_repository.count_reviews(user.id))
        return ApiResponse(
            responseCode=200,
            message="User retrieved successfully",
            data=AdminUserDetailRead(
                **base.model_dump(),
                reviews=[
                    self.provider_review_service._review_to_schema(review) for review in reviews
                ],
            ),
        )

    def list_user_reviews(
        self,
        user_id: int,
        *,
        page: int,
        per_page: int,
    ):
        user = self._get_user_or_raise(user_id)
        rows, total = self.user_repository.list_reviews(user.id, page=page, per_page=per_page)
        return build_paginated_response(
            items=self.provider_review_service._reviews_to_schema(rows),
            page=page,
            per_page=per_page,
            total=total,
            message="User reviews retrieved successfully",
        )

    def suspend_user(
        self,
        user_id: int,
        *,
        reason: str | None,
        current_user: AuthenticatedUser,
    ) -> ApiResponse[AdminUserRead]:
        user = self._get_user_or_raise(user_id)
        if user.role == UserRole.ADMIN:
            raise BadRequestError("Admin users cannot be suspended from this endpoint")
        old_values = {"status": user.status.value, "is_active": user.is_active}
        updated = self.user_repository.update(
            user,
            status=UserStatus.SUSPENDED,
            is_active=False,
            suspended_at=datetime.now(UTC),
            suspended_reason=reason,
        )
        self.audit_log_service.record(
            action="user.suspended",
            entity_type="user",
            entity_id=updated.id,
            actor_user_id=current_user.id,
            old_values=old_values,
            new_values={"status": updated.status.value, "is_active": updated.is_active},
            note=reason,
        )
        return ApiResponse(
            responseCode=200,
            message="User suspended successfully",
            data=self._user_to_schema(
                updated, reviews_count=self.user_repository.count_reviews(updated.id)
            ),
        )

    def activate_user(
        self, user_id: int, *, current_user: AuthenticatedUser
    ) -> ApiResponse[AdminUserRead]:
        user = self._get_user_or_raise(user_id)
        old_values = {"status": user.status.value, "is_active": user.is_active}
        next_status = UserStatus.ACTIVE if user.is_verified else UserStatus.UNVERIFIED
        updated = self.user_repository.update(
            user,
            status=next_status,
            is_active=True,
            suspended_at=None,
            suspended_reason=None,
        )
        self.audit_log_service.record(
            action="user.activated",
            entity_type="user",
            entity_id=updated.id,
            actor_user_id=current_user.id,
            old_values=old_values,
            new_values={"status": updated.status.value, "is_active": updated.is_active},
        )
        return ApiResponse(
            responseCode=200,
            message="User activated successfully",
            data=self._user_to_schema(
                updated, reviews_count=self.user_repository.count_reviews(updated.id)
            ),
        )

    def resend_verification(
        self, user_id: int, *, current_user: AuthenticatedUser
    ) -> ApiResponse[dict]:
        user = self._get_user_or_raise(user_id)
        if user.is_verified:
            raise BadRequestError("Email address is already verified")
        self.auth_service.send_email_verification_otp_for_user(user)
        self.audit_log_service.record(
            action="user.verification_email_resent",
            entity_type="user",
            entity_id=user.id,
            actor_user_id=current_user.id,
            note=f"Resent verification email to {user.email}",
        )
        return ApiResponse(
            responseCode=200,
            message="Verification email resent successfully",
            data={"status": "sent"},
        )

    def create_my_deletion_request(
        self,
        payload: UserDeletionRequestCreate,
        current_user: AuthenticatedUser,
    ) -> ApiResponse[UserDeletionRequestRead]:
        existing = self.deletion_request_repository.get_open_for_user(current_user.id)
        if existing is not None:
            raise BadRequestError("You already have an active deletion request")
        now = datetime.now(UTC)
        request = self.deletion_request_repository.create(
            UserDeletionRequest(
                user_id=current_user.id,
                status=UserDeletionRequestStatus.REQUESTED,
                reason=payload.reason,
                requested_at=now,
                grace_ends_at=now + timedelta(days=USER_DELETION_GRACE_DAYS),
            )
        )
        loaded = self.deletion_request_repository.get_by_id(request.id)
        self.audit_log_service.record(
            action="user_deletion_request.created",
            entity_type="deletion_request",
            entity_id=request.id,
            actor_user_id=current_user.id,
            new_values={"status": UserDeletionRequestStatus.REQUESTED.value},
            note=payload.reason,
        )
        return ApiResponse(
            responseCode=201,
            message="Deletion request created successfully",
            data=self._deletion_request_to_schema(loaded or request),
        )

    def list_deletion_requests(
        self,
        *,
        page: int,
        per_page: int,
        status: str | None = None,
        search: str | None = None,
    ) -> ApiResponse[PaginatedData[UserDeletionRequestRead]]:
        status_enum = self._parse_deletion_status(status)
        rows, total = self.deletion_request_repository.list(
            page=page,
            per_page=per_page,
            status=status_enum,
            search=search,
        )
        return build_paginated_response(
            items=[self._deletion_request_to_schema(row) for row in rows],
            page=page,
            per_page=per_page,
            total=total,
            message="Deletion requests retrieved successfully",
        )

    def start_processing_deletion_request(
        self,
        request_id: int,
        *,
        payload: UserDeletionRequestStatusUpdate,
        current_user: AuthenticatedUser,
    ) -> ApiResponse[UserDeletionRequestRead]:
        request = self._get_deletion_request_or_raise(request_id)
        if request.status != UserDeletionRequestStatus.REQUESTED:
            raise BadRequestError("Only requested deletion requests can be moved to processing")
        return self._transition_deletion_request(
            request,
            status=UserDeletionRequestStatus.PROCESSING,
            current_user=current_user,
            note=payload.note,
            processing_started_at=datetime.now(UTC),
        )

    def complete_deletion_request(
        self,
        request_id: int,
        *,
        payload: UserDeletionRequestStatusUpdate,
        current_user: AuthenticatedUser,
    ) -> ApiResponse[UserDeletionRequestRead]:
        request = self._get_deletion_request_or_raise(request_id)
        if request.status not in {
            UserDeletionRequestStatus.REQUESTED,
            UserDeletionRequestStatus.PROCESSING,
        }:
            raise BadRequestError("Only requested or processing deletion requests can be completed")
        return self._transition_deletion_request(
            request,
            status=UserDeletionRequestStatus.COMPLETED,
            current_user=current_user,
            note=payload.note,
            completed_at=datetime.now(UTC),
        )

    def cancel_deletion_request(
        self,
        request_id: int,
        *,
        payload: UserDeletionRequestStatusUpdate,
        current_user: AuthenticatedUser,
    ) -> ApiResponse[UserDeletionRequestRead]:
        request = self._get_deletion_request_or_raise(request_id)
        if request.status == UserDeletionRequestStatus.COMPLETED:
            raise BadRequestError("Completed deletion requests cannot be cancelled")
        return self._transition_deletion_request(
            request,
            status=UserDeletionRequestStatus.CANCELLED,
            current_user=current_user,
            note=payload.note,
            cancelled_at=datetime.now(UTC),
        )

    def list_user_status_options(self) -> ApiResponse[list[UserStatusOptionRead]]:
        return ApiResponse(
            responseCode=200,
            message="User status options retrieved successfully",
            data=[
                UserStatusOptionRead(label=value.value.replace("_", " ").title(), value=value.value)
                for value in UserStatus
            ],
        )

    def _transition_deletion_request(
        self,
        request: UserDeletionRequest,
        *,
        status: UserDeletionRequestStatus,
        current_user: AuthenticatedUser,
        note: str | None,
        **extra_fields,
    ) -> ApiResponse[UserDeletionRequestRead]:
        old_status = request.status
        updated = self.deletion_request_repository.update(
            request,
            status=status,
            processed_by_user_id=current_user.id,
            admin_note=note,
            **extra_fields,
        )
        self.audit_log_service.record(
            action="user_deletion_request.status_updated",
            entity_type="deletion_request",
            entity_id=updated.id,
            actor_user_id=current_user.id,
            old_values={"status": old_status.value},
            new_values={"status": status.value},
            note=note,
        )
        loaded = self.deletion_request_repository.get_by_id(updated.id)
        return ApiResponse(
            responseCode=200,
            message="Deletion request updated successfully",
            data=self._deletion_request_to_schema(loaded or updated),
        )

    def _get_user_or_raise(self, user_id: int):
        user = self.user_repository.get_by_id(user_id)
        if user is None:
            raise NotFoundError("User not found", data={"user_id": user_id})
        return user

    def _get_deletion_request_or_raise(self, request_id: int) -> UserDeletionRequest:
        request = self.deletion_request_repository.get_by_id(request_id)
        if request is None:
            raise NotFoundError("Deletion request not found", data={"request_id": request_id})
        return request

    @staticmethod
    def _user_name(user) -> str:
        return (
            " ".join(part for part in [user.first_name, user.last_name] if part).strip()
            or user.email
        )

    def _user_to_schema(self, user, *, reviews_count: int) -> AdminUserRead:
        return AdminUserRead(
            id=user.id,
            email=user.email,
            first_name=user.first_name,
            last_name=user.last_name,
            name=self._user_name(user),
            phone_number=user.phone_number,
            role=user.role.value,
            admin_type=user.admin_type.value if user.admin_type else None,
            status=user.status.value,
            is_active=user.is_active,
            is_verified=user.is_verified,
            is_phone_verified=user.is_phone_verified,
            reviews_count=reviews_count,
            last_active_at=user.last_login_at,
            joined_at=user.created_at,
            suspended_at=user.suspended_at,
            suspended_reason=user.suspended_reason,
        )

    def _deletion_request_to_schema(self, request: UserDeletionRequest) -> UserDeletionRequestRead:
        return UserDeletionRequestRead(
            id=request.id,
            user=UserDeletionRequestUserRead(
                id=request.user.id,
                email=request.user.email,
                first_name=request.user.first_name,
                last_name=request.user.last_name,
                name=self._user_name(request.user),
            ),
            status=request.status,
            reason=request.reason,
            requested_at=request.requested_at,
            grace_ends_at=request.grace_ends_at,
            processing_started_at=request.processing_started_at,
            completed_at=request.completed_at,
            cancelled_at=request.cancelled_at,
            processed_by_user_id=request.processed_by_user_id,
            admin_note=request.admin_note,
            created_at=request.created_at,
            updated_at=request.updated_at,
        )

    @staticmethod
    def _parse_user_status(status: str | None) -> UserStatus | None:
        if not status or status == "all":
            return None
        try:
            return UserStatus(status.lower())
        except ValueError as exc:
            raise BadRequestError(
                "Invalid user status",
                data={"status": status, "allowed_values": [value.value for value in UserStatus]},
            ) from exc

    @staticmethod
    def _parse_deletion_status(status: str | None) -> UserDeletionRequestStatus | None:
        if not status or status == "all":
            return None
        try:
            return UserDeletionRequestStatus(status.lower())
        except ValueError as exc:
            raise BadRequestError(
                "Invalid deletion request status",
                data={
                    "status": status,
                    "allowed_values": [value.value for value in UserDeletionRequestStatus],
                },
            ) from exc
