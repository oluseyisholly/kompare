from __future__ import annotations

from sqlalchemy.orm import Session, joinedload

from app.models.enums import UserDeletionRequestStatus
from app.models.user import User
from app.models.user_deletion_request import UserDeletionRequest
from app.repositories.pagination import paginate_query


class UserDeletionRequestRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, request_id: int) -> UserDeletionRequest | None:
        return (
            self.db.query(UserDeletionRequest)
            .options(
                joinedload(UserDeletionRequest.user),
                joinedload(UserDeletionRequest.processed_by_user),
            )
            .filter(UserDeletionRequest.id == request_id)
            .first()
        )

    def get_open_for_user(self, user_id: int) -> UserDeletionRequest | None:
        return (
            self.db.query(UserDeletionRequest)
            .filter(
                UserDeletionRequest.user_id == user_id,
                UserDeletionRequest.status.in_(
                    [
                        UserDeletionRequestStatus.REQUESTED,
                        UserDeletionRequestStatus.PROCESSING,
                    ]
                ),
            )
            .first()
        )

    def create(self, deletion_request: UserDeletionRequest) -> UserDeletionRequest:
        self.db.add(deletion_request)
        self.db.commit()
        self.db.refresh(deletion_request)
        return deletion_request

    def update(self, deletion_request: UserDeletionRequest, **fields) -> UserDeletionRequest:
        for key, value in fields.items():
            setattr(deletion_request, key, value)
        self.db.add(deletion_request)
        self.db.commit()
        self.db.refresh(deletion_request)
        return deletion_request

    def list(
        self,
        *,
        page: int,
        per_page: int,
        status: UserDeletionRequestStatus | None = None,
        search: str | None = None,
    ) -> tuple[list[UserDeletionRequest], int]:
        query = (
            self.db.query(UserDeletionRequest)
            .options(
                joinedload(UserDeletionRequest.user),
                joinedload(UserDeletionRequest.processed_by_user),
            )
            .order_by(UserDeletionRequest.requested_at.desc(), UserDeletionRequest.id.desc())
        )
        if status is not None:
            query = query.filter(UserDeletionRequest.status == status)
        if search:
            query = query.join(UserDeletionRequest.user).filter(
                User.email.ilike(f"%{search.strip()}%")
            )
        return paginate_query(query, page=page, per_page=per_page)
