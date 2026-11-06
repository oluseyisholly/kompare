from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.models.enums import ProviderReviewStatus, ProviderReviewTag, ProviderReviewType
from app.models.provider_review import ProviderReview, ProviderReviewComment, ProviderReviewVote
from app.repositories.pagination import paginate_query


class ProviderReviewRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, review_id: int) -> ProviderReview | None:
        return (
            self.db.query(ProviderReview)
            .options(joinedload(ProviderReview.provider), joinedload(ProviderReview.user))
            .filter(ProviderReview.id == review_id)
            .first()
        )

    def get_by_provider_and_user(
        self, provider_id: int, user_id: int | None
    ) -> ProviderReview | None:
        if user_id is None:
            return None
        return (
            self.db.query(ProviderReview)
            .filter(
                ProviderReview.provider_id == provider_id,
                ProviderReview.user_id == user_id,
                ProviderReview.review_type == ProviderReviewType.REVIEW,
            )
            .first()
        )

    def list_by_provider(
        self,
        provider_id: int,
        *,
        page: int,
        per_page: int,
        tags: list[ProviderReviewTag] | None = None,
        rating: int | None = None,
        status: ProviderReviewStatus = ProviderReviewStatus.PUBLISHED,
        review_type: ProviderReviewType = ProviderReviewType.REVIEW,
    ) -> tuple[list[ProviderReview], int]:
        query = (
            self.db.query(ProviderReview)
            .options(joinedload(ProviderReview.provider), joinedload(ProviderReview.user))
            .filter(
                ProviderReview.provider_id == provider_id,
                ProviderReview.status == status,
                ProviderReview.review_type == review_type,
            )
            .order_by(ProviderReview.reviewed_at.desc(), ProviderReview.id.desc())
        )
        if rating is not None:
            query = query.filter(ProviderReview.rating == rating)
        if tags:
            query = query.filter(ProviderReview.tags.contains([tag.value for tag in tags]))
        return paginate_query(query, page=page, per_page=per_page)

    def get_summary_by_provider(self, provider_id: int) -> tuple[float | None, int, dict[int, int]]:
        average_rating, total_reviews = (
            self.db.query(func.avg(ProviderReview.rating), func.count(ProviderReview.id))
            .filter(
                ProviderReview.provider_id == provider_id,
                ProviderReview.status == ProviderReviewStatus.PUBLISHED,
                ProviderReview.review_type == ProviderReviewType.REVIEW,
            )
            .one()
        )
        rating_rows = (
            self.db.query(ProviderReview.rating, func.count(ProviderReview.id))
            .filter(
                ProviderReview.provider_id == provider_id,
                ProviderReview.status == ProviderReviewStatus.PUBLISHED,
                ProviderReview.review_type == ProviderReviewType.REVIEW,
            )
            .group_by(ProviderReview.rating)
            .all()
        )
        return (
            float(average_rating) if average_rating is not None else None,
            int(total_reviews or 0),
            {rating: count for rating, count in rating_rows},
        )

    def list_for_admin(
        self,
        *,
        page: int,
        per_page: int,
        status: ProviderReviewStatus | None = None,
        provider_id: int | None = None,
        review_type: ProviderReviewType | None = None,
    ) -> tuple[list[ProviderReview], int]:
        query = (
            self.db.query(ProviderReview)
            .options(joinedload(ProviderReview.provider), joinedload(ProviderReview.user))
            .order_by(ProviderReview.reviewed_at.desc(), ProviderReview.id.desc())
        )
        if status is not None:
            query = query.filter(ProviderReview.status == status)
        if provider_id is not None:
            query = query.filter(ProviderReview.provider_id == provider_id)
        if review_type is not None:
            query = query.filter(ProviderReview.review_type == review_type)
        return paginate_query(query, page=page, per_page=per_page)

    def create(self, review: ProviderReview) -> ProviderReview:
        self.db.add(review)
        self.db.commit()
        self.db.refresh(review)
        return review

    def update(self, review: ProviderReview, **fields) -> ProviderReview:
        for key, value in fields.items():
            setattr(review, key, value)
        self.db.add(review)
        self.db.commit()
        self.db.refresh(review)
        return review

    def count_comments(self, review_id: int) -> int:
        return (
            self.db.query(func.count(ProviderReviewComment.id))
            .filter(
                ProviderReviewComment.review_id == review_id,
                ProviderReviewComment.status == ProviderReviewStatus.PUBLISHED,
            )
            .scalar()
            or 0
        )

    def count_votes(self, review_id: int, *, is_helpful: bool) -> int:
        return (
            self.db.query(func.count(ProviderReviewVote.id))
            .filter(
                ProviderReviewVote.review_id == review_id,
                ProviderReviewVote.is_helpful.is_(is_helpful),
            )
            .scalar()
            or 0
        )

    def list_comments(
        self,
        review_id: int,
        *,
        page: int,
        per_page: int,
    ) -> tuple[list[ProviderReviewComment], int]:
        query = (
            self.db.query(ProviderReviewComment)
            .options(joinedload(ProviderReviewComment.user))
            .filter(
                ProviderReviewComment.review_id == review_id,
                ProviderReviewComment.status == ProviderReviewStatus.PUBLISHED,
            )
            .order_by(ProviderReviewComment.created_at.asc(), ProviderReviewComment.id.asc())
        )
        return paginate_query(query, page=page, per_page=per_page)

    def get_comment_by_id(self, comment_id: int) -> ProviderReviewComment | None:
        return (
            self.db.query(ProviderReviewComment)
            .options(joinedload(ProviderReviewComment.user))
            .filter(ProviderReviewComment.id == comment_id)
            .first()
        )

    def list_comments_for_admin(
        self,
        *,
        page: int,
        per_page: int,
        status: ProviderReviewStatus | None = None,
        review_id: int | None = None,
    ) -> tuple[list[ProviderReviewComment], int]:
        query = (
            self.db.query(ProviderReviewComment)
            .options(joinedload(ProviderReviewComment.user))
            .order_by(ProviderReviewComment.created_at.desc(), ProviderReviewComment.id.desc())
        )
        if status is not None:
            query = query.filter(ProviderReviewComment.status == status)
        if review_id is not None:
            query = query.filter(ProviderReviewComment.review_id == review_id)
        return paginate_query(query, page=page, per_page=per_page)

    def create_comment(self, comment: ProviderReviewComment) -> ProviderReviewComment:
        self.db.add(comment)
        self.db.commit()
        self.db.refresh(comment)
        return comment

    def update_comment(self, comment: ProviderReviewComment, **fields) -> ProviderReviewComment:
        for key, value in fields.items():
            setattr(comment, key, value)
        self.db.add(comment)
        self.db.commit()
        self.db.refresh(comment)
        return comment

    def get_vote(self, review_id: int, user_id: int) -> ProviderReviewVote | None:
        return (
            self.db.query(ProviderReviewVote)
            .filter(
                ProviderReviewVote.review_id == review_id,
                ProviderReviewVote.user_id == user_id,
            )
            .first()
        )

    def upsert_vote(self, vote: ProviderReviewVote, *, is_helpful: bool) -> ProviderReviewVote:
        existing = self.get_vote(vote.review_id, vote.user_id)
        if existing is not None:
            existing.is_helpful = is_helpful
            self.db.add(existing)
            self.db.commit()
            self.db.refresh(existing)
            return existing
        self.db.add(vote)
        self.db.commit()
        self.db.refresh(vote)
        return vote

    def delete_vote(self, vote: ProviderReviewVote) -> None:
        self.db.delete(vote)
        self.db.commit()

    def engagement_counts(self, review_ids):
        from sqlalchemy import case

        if not review_ids:
            return {}
        result = {key: {"helpful": 0, "not_helpful": 0, "comments": 0} for key in review_ids}
        votes = (
            self.db.query(
                ProviderReviewVote.review_id,
                func.sum(case((ProviderReviewVote.is_helpful.is_(True), 1), else_=0)),
                func.sum(case((ProviderReviewVote.is_helpful.is_(False), 1), else_=0)),
            )
            .filter(ProviderReviewVote.review_id.in_(review_ids))
            .group_by(ProviderReviewVote.review_id)
            .all()
        )
        for key, helpful, not_helpful in votes:
            result[key].update(helpful=int(helpful), not_helpful=int(not_helpful))
        comments = (
            self.db.query(ProviderReviewComment.review_id, func.count(ProviderReviewComment.id))
            .filter(
                ProviderReviewComment.review_id.in_(review_ids),
                ProviderReviewComment.status == ProviderReviewStatus.PUBLISHED,
            )
            .group_by(ProviderReviewComment.review_id)
            .all()
        )
        for key, count in comments:
            result[key]["comments"] = count
        return result
