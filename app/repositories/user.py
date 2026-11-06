from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from app.models.enums import ProviderReviewType, UserStatus
from app.models.provider_review import ProviderReview
from app.models.user import User
from app.repositories.pagination import paginate_query


class UserRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_email(self, email: str, *, for_update: bool = False) -> User | None:
        query = self.db.query(User).filter(User.email == email.lower())
        if for_update:
            query = query.with_for_update().populate_existing()
        return query.first()

    def get_by_id(self, user_id: int) -> User | None:
        return self.db.query(User).filter(User.id == user_id).first()

    def list_for_admin(
        self,
        *,
        page: int,
        per_page: int,
        search: str | None = None,
        status: UserStatus | None = None,
    ):
        review_counts = (
            self.db.query(
                ProviderReview.user_id, func.count(ProviderReview.id).label("reviews_count")
            )
            .filter(
                ProviderReview.user_id.isnot(None),
                ProviderReview.review_type == ProviderReviewType.REVIEW,
            )
            .group_by(ProviderReview.user_id)
            .subquery()
        )
        query = (
            self.db.query(
                User, func.coalesce(review_counts.c.reviews_count, 0).label("reviews_count")
            )
            .outerjoin(review_counts, review_counts.c.user_id == User.id)
            .order_by(User.created_at.desc(), User.id.desc())
        )
        if search:
            value = f"%{search.strip()}%"
            query = query.filter(
                or_(
                    User.email.ilike(value),
                    User.first_name.ilike(value),
                    User.last_name.ilike(value),
                    User.phone_number.ilike(value),
                )
            )
        if status is not None:
            query = query.filter(User.status == status)
        return paginate_query(query, page=page, per_page=per_page)

    def count_reviews(self, user_id: int) -> int:
        return int(
            self.db.query(func.count(ProviderReview.id))
            .filter(
                ProviderReview.user_id == user_id,
                ProviderReview.review_type == ProviderReviewType.REVIEW,
            )
            .scalar()
            or 0
        )

    def list_reviews(self, user_id: int, *, page: int, per_page: int):
        query = (
            self.db.query(ProviderReview)
            .options(joinedload(ProviderReview.user), joinedload(ProviderReview.provider))
            .filter(
                ProviderReview.user_id == user_id,
                ProviderReview.review_type == ProviderReviewType.REVIEW,
            )
            .order_by(ProviderReview.reviewed_at.desc(), ProviderReview.id.desc())
        )
        return paginate_query(query, page=page, per_page=per_page)

    def create(self, user: User) -> User:
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def add(self, user: User) -> User:
        self.db.add(user)
        self.db.flush()
        self.db.refresh(user)
        return user

    def mark_login(self, user: User, *, commit: bool = True) -> User:
        user.last_login_at = datetime.now(UTC)
        self.db.add(user)
        self.db.flush()
        if commit:
            self.db.commit()
        self.db.refresh(user)
        return user

    def update(self, user: User, **fields) -> User:
        for key, value in fields.items():
            setattr(user, key, value)
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def mark_verified(self, user: User) -> User:
        user.is_verified = True
        user.status = UserStatus.ACTIVE
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def mark_verified_without_commit(self, user: User) -> User:
        user.is_verified = True
        user.status = UserStatus.ACTIVE
        self.db.add(user)
        self.db.flush()
        self.db.refresh(user)
        return user
