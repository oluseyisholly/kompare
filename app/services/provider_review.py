from __future__ import annotations

from app.core.exceptions import BadRequestError, ConflictError, NotFoundError
from app.models.enums import (
    ProviderReviewStatus,
    ProviderReviewTag,
    ProviderReviewType,
    ProviderTipCategory,
    ProviderTipSeverity,
)
from app.models.provider_review import ProviderReview, ProviderReviewComment, ProviderReviewVote
from app.repositories.provider import ProviderRepository
from app.repositories.provider_review import ProviderReviewRepository
from app.schemas.auth import AuthenticatedUser
from app.schemas.common import ApiResponse, PaginatedData, build_paginated_response
from app.schemas.provider_review import (
    ProviderReviewCommentCreate,
    ProviderReviewCommentRead,
    ProviderReviewCreate,
    ProviderReviewRead,
    ProviderReviewStatusUpdate,
    ProviderReviewSummary,
    ProviderReviewUpdate,
    ProviderReviewVoteSummary,
    ProviderReviewVoteUpsert,
    ProviderTipCreate,
    ReviewUserRead,
)
from app.services.audit_log import AuditLogService
from app.services.provider_metric import ProviderMetricService


class ProviderReviewService:
    def __init__(
        self,
        repository: ProviderReviewRepository,
        provider_repository: ProviderRepository,
        audit_log_service: AuditLogService,
        provider_metric_service: ProviderMetricService,
    ) -> None:
        self.repository = repository
        self.provider_repository = provider_repository
        self.audit_log_service = audit_log_service
        self.provider_metric_service = provider_metric_service

    def _get_provider_or_raise(self, slug: str):
        provider = self.provider_repository.get_by_slug(slug)
        if provider is None:
            raise NotFoundError("Provider not found", data={"slug": slug})
        return provider

    @staticmethod
    def _parse_tags(tags: list[str] | None) -> list[ProviderReviewTag]:
        parsed: list[ProviderReviewTag] = []
        for tag in tags or []:
            try:
                parsed.append(ProviderReviewTag(tag))
            except ValueError as exc:
                raise BadRequestError(
                    "Invalid review tag",
                    data={
                        "tag": tag,
                        "allowed_values": [value.value for value in ProviderReviewTag],
                    },
                ) from exc
        return parsed

    @staticmethod
    def _review_user(user) -> ReviewUserRead:
        if user is None:
            return ReviewUserRead(
                id=None,
                first_name="Anonymous",
                last_name=None,
                is_anonymous=True,
            )
        return ReviewUserRead(
            id=user.id,
            first_name=user.first_name,
            last_name=user.last_name,
            is_anonymous=False,
        )

    @staticmethod
    def _tip_severity_for_category(category: ProviderTipCategory) -> ProviderTipSeverity:
        severity_map = {
            ProviderTipCategory.RATE_ALERT: ProviderTipSeverity.MEDIUM,
            ProviderTipCategory.HIDDEN_FEE_WARNING: ProviderTipSeverity.HIGH,
            ProviderTipCategory.SCAM_WARNING: ProviderTipSeverity.CRITICAL,
            ProviderTipCategory.GENERAL_TIP: ProviderTipSeverity.LOW,
        }
        return severity_map[category]

    def _review_to_schema(self, review: ProviderReview, counts=None) -> ProviderReviewRead:
        return ProviderReviewRead(
            id=review.id,
            provider_id=review.provider_id,
            provider_slug=review.provider.slug,
            user=self._review_user(review.user),
            review_type=review.review_type,
            tip_category=review.tip_category,
            tip_severity=review.tip_severity,
            rating=review.rating,
            title=review.title,
            body=review.body,
            tags=review.tags or [],
            status=review.status.value,
            is_verified=review.is_verified,
            reviewed_at=review.reviewed_at,
            helpful_count=counts["helpful"]
            if counts is not None
            else self.repository.count_votes(review.id, is_helpful=True),
            not_helpful_count=counts["not_helpful"]
            if counts is not None
            else self.repository.count_votes(review.id, is_helpful=False),
            comments_count=counts["comments"]
            if counts is not None
            else self.repository.count_comments(review.id),
            created_at=review.created_at,
            updated_at=review.updated_at,
        )

    def _reviews_to_schema(self, rows):
        counts = self.repository.engagement_counts([row.id for row in rows])
        return [self._review_to_schema(row, counts=counts[row.id]) for row in rows]

    def _comment_to_schema(self, comment: ProviderReviewComment) -> ProviderReviewCommentRead:
        return ProviderReviewCommentRead(
            id=comment.id,
            review_id=comment.review_id,
            user=self._review_user(comment.user),
            body=comment.body,
            status=comment.status.value,
            created_at=comment.created_at,
            updated_at=comment.updated_at,
        )

    def list_provider_reviews(
        self,
        slug: str,
        *,
        page: int,
        per_page: int,
        tags: list[str] | None,
        rating: int | None,
    ) -> ApiResponse[PaginatedData[ProviderReviewRead]]:
        provider = self._get_provider_or_raise(slug)
        parsed_tags = self._parse_tags(tags)
        rows, total = self.repository.list_by_provider(
            provider.id,
            page=page,
            per_page=per_page,
            tags=parsed_tags,
            rating=rating,
            review_type=ProviderReviewType.REVIEW,
        )
        return build_paginated_response(
            items=self._reviews_to_schema(rows),
            page=page,
            per_page=per_page,
            total=total,
            message="Provider reviews retrieved successfully",
        )

    def get_provider_review_summary(self, slug: str) -> ApiResponse[ProviderReviewSummary]:
        provider = self._get_provider_or_raise(slug)
        average_rating, total_reviews, rating_counts = self.repository.get_summary_by_provider(
            provider.id
        )
        return ApiResponse(
            responseCode=200,
            message="Provider review summary retrieved successfully",
            data=ProviderReviewSummary(
                provider_slug=provider.slug,
                average_rating=round(average_rating, 2) if average_rating is not None else None,
                total_reviews=total_reviews,
                rating_counts={str(rating): rating_counts.get(rating, 0) for rating in range(1, 6)},
            ),
        )

    def create_provider_review(
        self,
        slug: str,
        payload: ProviderReviewCreate,
        current_user: AuthenticatedUser | None,
    ) -> ApiResponse[ProviderReviewRead]:
        provider = self._get_provider_or_raise(slug)
        user_id = current_user.id if current_user else None
        if user_id is not None:
            existing = self.repository.get_by_provider_and_user(provider.id, user_id)
            if existing is not None:
                raise ConflictError(
                    "You have already reviewed this provider",
                    data={"provider": provider.slug, "review_id": existing.id},
                )

        review = self.repository.create(
            ProviderReview(
                provider_id=provider.id,
                user_id=user_id,
                review_type=ProviderReviewType.REVIEW,
                tip_category=None,
                tip_severity=None,
                rating=payload.rating,
                title=payload.title,
                body=payload.body,
                tags=[tag.value for tag in payload.tags],
                status=ProviderReviewStatus.PENDING,
                is_verified=False,
            )
        )
        loaded_review = self.repository.get_by_id(review.id)
        if loaded_review is None:
            raise NotFoundError(
                "Provider review not found after creation", data={"review_id": review.id}
            )
        return ApiResponse(
            responseCode=201,
            message="Provider review created successfully",
            data=self._review_to_schema(loaded_review),
        )

    def list_provider_tips(
        self,
        slug: str,
        *,
        page: int,
        per_page: int,
    ) -> ApiResponse[PaginatedData[ProviderReviewRead]]:
        provider = self._get_provider_or_raise(slug)
        rows, total = self.repository.list_by_provider(
            provider.id,
            page=page,
            per_page=per_page,
            review_type=ProviderReviewType.TIP,
        )
        return build_paginated_response(
            items=self._reviews_to_schema(rows),
            page=page,
            per_page=per_page,
            total=total,
            message="Provider tips retrieved successfully",
        )

    def create_provider_tip(
        self,
        slug: str,
        payload: ProviderTipCreate,
    ) -> ApiResponse[ProviderReviewRead]:
        provider = self._get_provider_or_raise(slug)
        tip = self.repository.create(
            ProviderReview(
                provider_id=provider.id,
                user_id=None,
                review_type=ProviderReviewType.TIP,
                tip_category=payload.tip_category,
                tip_severity=self._tip_severity_for_category(payload.tip_category),
                rating=None,
                title=None,
                body=payload.body,
                tags=[],
                status=ProviderReviewStatus.PENDING,
                is_verified=False,
            )
        )
        loaded_tip = self.repository.get_by_id(tip.id)
        if loaded_tip is None:
            raise NotFoundError("Provider tip not found after creation", data={"tip_id": tip.id})
        return ApiResponse(
            responseCode=201,
            message="Provider tip created successfully",
            data=self._review_to_schema(loaded_tip),
        )

    def update_my_provider_review(
        self,
        slug: str,
        payload: ProviderReviewUpdate,
        current_user: AuthenticatedUser,
    ) -> ApiResponse[ProviderReviewRead]:
        provider = self._get_provider_or_raise(slug)
        review = self.repository.get_by_provider_and_user(provider.id, current_user.id)
        if review is None:
            raise NotFoundError(
                "You have not reviewed this provider yet",
                data={"provider": provider.slug},
            )

        fields = payload.model_dump(exclude_unset=True)
        if "tags" in fields:
            fields["tags"] = [tag.value for tag in payload.tags or []]
        if not fields:
            raise BadRequestError("No review fields were provided for update")
        fields["status"] = ProviderReviewStatus.PENDING
        fields["is_verified"] = False

        updated = self.repository.update(review, **fields)
        loaded_review = self.repository.get_by_id(updated.id)
        if loaded_review is None:
            raise NotFoundError(
                "Provider review not found after update", data={"review_id": updated.id}
            )

        return ApiResponse(
            responseCode=200,
            message="Provider review updated successfully",
            data=self._review_to_schema(loaded_review),
        )

    def list_reviews_for_admin(
        self,
        *,
        page: int,
        per_page: int,
        status: str | None,
        provider_slug: str | None,
        review_type: str | None,
    ) -> ApiResponse[PaginatedData[ProviderReviewRead]]:
        provider_id = None
        if provider_slug is not None:
            provider = self._get_provider_or_raise(provider_slug)
            provider_id = provider.id

        status_enum = None
        if status is not None:
            try:
                status_enum = ProviderReviewStatus(status.lower())
            except ValueError as exc:
                raise BadRequestError(
                    "Invalid review status",
                    data={
                        "status": status,
                        "allowed_values": [value.value for value in ProviderReviewStatus],
                    },
                ) from exc

        review_type_enum = None
        if review_type is not None:
            try:
                review_type_enum = ProviderReviewType(review_type.lower())
            except ValueError as exc:
                raise BadRequestError(
                    "Invalid review type",
                    data={
                        "review_type": review_type,
                        "allowed_values": [value.value for value in ProviderReviewType],
                    },
                ) from exc

        rows, total = self.repository.list_for_admin(
            page=page,
            per_page=per_page,
            status=status_enum,
            provider_id=provider_id,
            review_type=review_type_enum,
        )
        return build_paginated_response(
            items=self._reviews_to_schema(rows),
            page=page,
            per_page=per_page,
            total=total,
            message="Provider reviews retrieved successfully",
        )

    def update_review_status(
        self,
        review_id: int,
        payload: ProviderReviewStatusUpdate,
        current_user: AuthenticatedUser,
    ) -> ApiResponse[ProviderReviewRead]:
        review = self.repository.get_by_id(review_id)
        if review is None:
            raise NotFoundError("Provider review not found", data={"review_id": review_id})

        old_status = review.status
        old_is_verified = review.is_verified
        is_verified = payload.status == ProviderReviewStatus.PUBLISHED
        updated = self.repository.update(review, status=payload.status, is_verified=is_verified)
        self.audit_log_service.record(
            action="provider_review.status_updated",
            entity_type="provider_review",
            entity_id=updated.id,
            actor_user_id=current_user.id,
            old_values={"status": old_status.value, "is_verified": old_is_verified},
            new_values={"status": payload.status.value, "is_verified": is_verified},
            metadata_json={"provider_id": updated.provider_id},
            note=payload.note,
        )
        provider = self.provider_repository.get_by_slug(updated.provider.slug)
        if provider is not None:
            self.provider_metric_service.refresh_provider(provider)
        loaded_review = self.repository.get_by_id(updated.id)
        if loaded_review is None:
            raise NotFoundError(
                "Provider review not found after status update", data={"review_id": updated.id}
            )

        return ApiResponse(
            responseCode=200,
            message="Provider review status updated successfully",
            data=self._review_to_schema(loaded_review),
        )

    def soft_delete_my_provider_review(
        self,
        slug: str,
        current_user: AuthenticatedUser,
    ) -> ApiResponse[dict]:
        provider = self._get_provider_or_raise(slug)
        review = self.repository.get_by_provider_and_user(provider.id, current_user.id)
        if review is None:
            raise NotFoundError(
                "You have not reviewed this provider yet", data={"provider": provider.slug}
            )
        self.repository.update(review, status=ProviderReviewStatus.HIDDEN, is_verified=False)
        self.provider_metric_service.refresh_provider(provider)
        return ApiResponse(
            responseCode=200,
            message="Provider review deleted successfully",
            data={"review_id": review.id, "status": ProviderReviewStatus.HIDDEN.value},
        )

    def soft_delete_review_for_admin(
        self,
        review_id: int,
        current_user: AuthenticatedUser,
    ) -> ApiResponse[dict]:
        review = self.repository.get_by_id(review_id)
        if review is None:
            raise NotFoundError("Provider review not found", data={"review_id": review_id})
        old_status = review.status
        old_is_verified = review.is_verified
        updated = self.repository.update(
            review, status=ProviderReviewStatus.HIDDEN, is_verified=False
        )
        self.audit_log_service.record(
            action="provider_review.deleted",
            entity_type="provider_review",
            entity_id=updated.id,
            actor_user_id=current_user.id,
            old_values={"status": old_status.value, "is_verified": old_is_verified},
            new_values={"status": ProviderReviewStatus.HIDDEN.value, "is_verified": False},
            metadata_json={"provider_id": updated.provider_id},
            note="Deleted by admin",
        )
        provider = self.provider_repository.get_by_slug(updated.provider.slug)
        if provider is not None:
            self.provider_metric_service.refresh_provider(provider)
        return ApiResponse(
            responseCode=200,
            message="Provider review deleted successfully",
            data={"review_id": review_id, "status": ProviderReviewStatus.HIDDEN.value},
        )

    def list_review_comments(
        self,
        review_id: int,
        *,
        page: int,
        per_page: int,
    ) -> ApiResponse[PaginatedData[ProviderReviewCommentRead]]:
        review = self.repository.get_by_id(review_id)
        if review is None or review.status != ProviderReviewStatus.PUBLISHED:
            raise NotFoundError("Provider review not found", data={"review_id": review_id})

        rows, total = self.repository.list_comments(review_id, page=page, per_page=per_page)
        return build_paginated_response(
            items=[self._comment_to_schema(row) for row in rows],
            page=page,
            per_page=per_page,
            total=total,
            message="Provider review comments retrieved successfully",
        )

    def create_review_comment(
        self,
        review_id: int,
        payload: ProviderReviewCommentCreate,
        current_user: AuthenticatedUser | None,
    ) -> ApiResponse[ProviderReviewCommentRead]:
        review = self.repository.get_by_id(review_id)
        if review is None or review.status != ProviderReviewStatus.PUBLISHED:
            raise NotFoundError("Provider review not found", data={"review_id": review_id})

        comment = self.repository.create_comment(
            ProviderReviewComment(
                review_id=review.id,
                user_id=current_user.id if current_user else None,
                body=payload.body,
                status=ProviderReviewStatus.PUBLISHED,
            )
        )
        loaded_comment = self.repository.get_comment_by_id(comment.id)
        if loaded_comment is None:
            raise NotFoundError(
                "Provider review comment not found after creation", data={"comment_id": comment.id}
            )
        return ApiResponse(
            responseCode=201,
            message="Provider review comment created successfully",
            data=self._comment_to_schema(loaded_comment),
        )

    def list_comments_for_admin(
        self,
        *,
        page: int,
        per_page: int,
        status: str | None,
        review_id: int | None,
    ) -> ApiResponse[PaginatedData[ProviderReviewCommentRead]]:
        status_enum = None
        if status is not None:
            try:
                status_enum = ProviderReviewStatus(status.lower())
            except ValueError as exc:
                raise BadRequestError(
                    "Invalid comment status",
                    data={
                        "status": status,
                        "allowed_values": [value.value for value in ProviderReviewStatus],
                    },
                ) from exc
        rows, total = self.repository.list_comments_for_admin(
            page=page,
            per_page=per_page,
            status=status_enum,
            review_id=review_id,
        )
        return build_paginated_response(
            items=[self._comment_to_schema(row) for row in rows],
            page=page,
            per_page=per_page,
            total=total,
            message="Provider review comments retrieved successfully",
        )

    def soft_delete_comment_for_admin(
        self, comment_id: int, current_user: AuthenticatedUser
    ) -> ApiResponse[dict]:
        comment = self.repository.get_comment_by_id(comment_id)
        if comment is None:
            raise NotFoundError(
                "Provider review comment not found", data={"comment_id": comment_id}
            )
        old_status = comment.status
        updated = self.repository.update_comment(comment, status=ProviderReviewStatus.HIDDEN)
        self.audit_log_service.record(
            action="provider_review_comment.deleted",
            entity_type="provider_review_comment",
            entity_id=updated.id,
            actor_user_id=current_user.id,
            old_values={"status": old_status.value},
            new_values={"status": ProviderReviewStatus.HIDDEN.value},
            metadata_json={"review_id": updated.review_id},
            note="Deleted by admin",
        )
        return ApiResponse(
            responseCode=200,
            message="Provider review comment deleted successfully",
            data={"comment_id": comment_id, "status": ProviderReviewStatus.HIDDEN.value},
        )

    def vote_on_review(
        self,
        review_id: int,
        payload: ProviderReviewVoteUpsert,
        current_user: AuthenticatedUser,
    ) -> ApiResponse[ProviderReviewVoteSummary]:
        review = self.repository.get_by_id(review_id)
        if review is None or review.status != ProviderReviewStatus.PUBLISHED:
            raise NotFoundError("Provider review not found", data={"review_id": review_id})

        self.repository.upsert_vote(
            ProviderReviewVote(
                review_id=review_id,
                user_id=current_user.id,
                is_helpful=payload.is_helpful,
            ),
            is_helpful=payload.is_helpful,
        )

        return ApiResponse(
            responseCode=200,
            message="Provider review vote saved successfully",
            data=ProviderReviewVoteSummary(
                review_id=review_id,
                helpful_count=self.repository.count_votes(review_id, is_helpful=True),
                not_helpful_count=self.repository.count_votes(review_id, is_helpful=False),
            ),
        )

    def remove_review_vote(
        self,
        review_id: int,
        current_user: AuthenticatedUser,
    ) -> ApiResponse[ProviderReviewVoteSummary]:
        vote = self.repository.get_vote(review_id, current_user.id)
        if vote is not None:
            self.repository.delete_vote(vote)

        return ApiResponse(
            responseCode=200,
            message="Provider review vote removed",
            data=ProviderReviewVoteSummary(
                review_id=review_id,
                helpful_count=self.repository.count_votes(review_id, is_helpful=True),
                not_helpful_count=self.repository.count_votes(review_id, is_helpful=False),
            ),
        )
