from fastapi import APIRouter, Depends, Query

from app.dependencies.auth import get_current_user, get_optional_current_user, require_admin
from app.dependencies.providers import get_provider_review_service
from app.models.enums import ProviderReviewTag, ProviderTipCategory
from app.schemas.auth import AuthenticatedUser
from app.schemas.common import ApiResponse, PaginatedData
from app.schemas.provider_review import (
    EnumOptionRead,
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
)
from app.services.provider_review import ProviderReviewService

router = APIRouter(tags=["Provider Reviews"])


def _enum_option(value: str) -> EnumOptionRead:
    return EnumOptionRead(
        value=value,
        label=value.replace("_", " ").title(),
    )


@router.get("/providers/reviews/tags", response_model=ApiResponse[list[EnumOptionRead]])
def list_provider_review_tags() -> ApiResponse[list[EnumOptionRead]]:
    return ApiResponse(
        responseCode=200,
        message="Provider review tags retrieved successfully",
        data=[_enum_option(tag.value) for tag in ProviderReviewTag],
    )


@router.get("/providers/tips/categories", response_model=ApiResponse[list[EnumOptionRead]])
def list_provider_tip_categories() -> ApiResponse[list[EnumOptionRead]]:
    return ApiResponse(
        responseCode=200,
        message="Provider tip categories retrieved successfully",
        data=[_enum_option(category.value) for category in ProviderTipCategory],
    )


@router.get(
    "/providers/{slug}/reviews", response_model=ApiResponse[PaginatedData[ProviderReviewRead]]
)
def list_provider_reviews(
    slug: str,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    tags: list[str] | None = Query(default=None),
    rating: int | None = Query(default=None, ge=1, le=5),
    service: ProviderReviewService = Depends(get_provider_review_service),
) -> ApiResponse[PaginatedData[ProviderReviewRead]]:
    return service.list_provider_reviews(
        slug,
        page=page,
        per_page=per_page,
        tags=tags,
        rating=rating,
    )


@router.get("/providers/{slug}/reviews/summary", response_model=ApiResponse[ProviderReviewSummary])
def get_provider_review_summary(
    slug: str,
    service: ProviderReviewService = Depends(get_provider_review_service),
) -> ApiResponse[ProviderReviewSummary]:
    return service.get_provider_review_summary(slug)


@router.get("/providers/{slug}/tips", response_model=ApiResponse[PaginatedData[ProviderReviewRead]])
def list_provider_tips(
    slug: str,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    service: ProviderReviewService = Depends(get_provider_review_service),
) -> ApiResponse[PaginatedData[ProviderReviewRead]]:
    return service.list_provider_tips(slug, page=page, per_page=per_page)


@router.post(
    "/providers/{slug}/tips", response_model=ApiResponse[ProviderReviewRead], status_code=201
)
def create_provider_tip(
    slug: str,
    payload: ProviderTipCreate,
    service: ProviderReviewService = Depends(get_provider_review_service),
) -> ApiResponse[ProviderReviewRead]:
    return service.create_provider_tip(slug, payload)


@router.get(
    "/admin/provider-reviews", response_model=ApiResponse[PaginatedData[ProviderReviewRead]]
)
def list_reviews_for_admin(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    status: str | None = Query(default=None),
    provider_slug: str | None = Query(default=None),
    review_type: str | None = Query(default=None),
    service: ProviderReviewService = Depends(get_provider_review_service),
    current_user: AuthenticatedUser = Depends(require_admin),
) -> ApiResponse[PaginatedData[ProviderReviewRead]]:
    del current_user
    return service.list_reviews_for_admin(
        page=page,
        per_page=per_page,
        status=status,
        provider_slug=provider_slug,
        review_type=review_type,
    )


@router.post(
    "/providers/{slug}/reviews", response_model=ApiResponse[ProviderReviewRead], status_code=201
)
def create_provider_review(
    slug: str,
    payload: ProviderReviewCreate,
    service: ProviderReviewService = Depends(get_provider_review_service),
    current_user: AuthenticatedUser | None = Depends(get_optional_current_user),
) -> ApiResponse[ProviderReviewRead]:
    return service.create_provider_review(slug, payload, current_user)


@router.patch("/providers/{slug}/reviews/me", response_model=ApiResponse[ProviderReviewRead])
def update_my_provider_review(
    slug: str,
    payload: ProviderReviewUpdate,
    service: ProviderReviewService = Depends(get_provider_review_service),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> ApiResponse[ProviderReviewRead]:
    return service.update_my_provider_review(slug, payload, current_user)


@router.delete("/providers/{slug}/reviews/me", response_model=ApiResponse[dict])
def delete_my_provider_review(
    slug: str,
    service: ProviderReviewService = Depends(get_provider_review_service),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> ApiResponse[dict]:
    return service.soft_delete_my_provider_review(slug, current_user)


@router.patch(
    "/admin/provider-reviews/{review_id}/status", response_model=ApiResponse[ProviderReviewRead]
)
def update_review_status(
    review_id: int,
    payload: ProviderReviewStatusUpdate,
    service: ProviderReviewService = Depends(get_provider_review_service),
    current_user: AuthenticatedUser = Depends(require_admin),
) -> ApiResponse[ProviderReviewRead]:
    return service.update_review_status(review_id, payload, current_user)


@router.delete("/admin/provider-reviews/{review_id}", response_model=ApiResponse[dict])
def delete_review_for_admin(
    review_id: int,
    service: ProviderReviewService = Depends(get_provider_review_service),
    current_user: AuthenticatedUser = Depends(require_admin),
) -> ApiResponse[dict]:
    return service.soft_delete_review_for_admin(review_id, current_user)


@router.get(
    "/admin/provider-review-comments",
    response_model=ApiResponse[PaginatedData[ProviderReviewCommentRead]],
)
def list_comments_for_admin(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    status: str | None = Query(default=None),
    review_id: int | None = Query(default=None, ge=1),
    service: ProviderReviewService = Depends(get_provider_review_service),
    current_user: AuthenticatedUser = Depends(require_admin),
) -> ApiResponse[PaginatedData[ProviderReviewCommentRead]]:
    del current_user
    return service.list_comments_for_admin(
        page=page,
        per_page=per_page,
        status=status,
        review_id=review_id,
    )


@router.delete("/admin/provider-review-comments/{comment_id}", response_model=ApiResponse[dict])
def delete_comment_for_admin(
    comment_id: int,
    service: ProviderReviewService = Depends(get_provider_review_service),
    current_user: AuthenticatedUser = Depends(require_admin),
) -> ApiResponse[dict]:
    return service.soft_delete_comment_for_admin(comment_id, current_user)


@router.get(
    "/provider-reviews/{review_id}/comments",
    response_model=ApiResponse[PaginatedData[ProviderReviewCommentRead]],
)
def list_review_comments(
    review_id: int,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    service: ProviderReviewService = Depends(get_provider_review_service),
) -> ApiResponse[PaginatedData[ProviderReviewCommentRead]]:
    return service.list_review_comments(review_id, page=page, per_page=per_page)


@router.post(
    "/provider-reviews/{review_id}/comments",
    response_model=ApiResponse[ProviderReviewCommentRead],
    status_code=201,
)
def create_review_comment(
    review_id: int,
    payload: ProviderReviewCommentCreate,
    service: ProviderReviewService = Depends(get_provider_review_service),
    current_user: AuthenticatedUser | None = Depends(get_optional_current_user),
) -> ApiResponse[ProviderReviewCommentRead]:
    return service.create_review_comment(review_id, payload, current_user)


@router.put(
    "/provider-reviews/{review_id}/vote", response_model=ApiResponse[ProviderReviewVoteSummary]
)
def vote_on_review(
    review_id: int,
    payload: ProviderReviewVoteUpsert,
    service: ProviderReviewService = Depends(get_provider_review_service),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> ApiResponse[ProviderReviewVoteSummary]:
    return service.vote_on_review(review_id, payload, current_user)


@router.delete(
    "/provider-reviews/{review_id}/vote", response_model=ApiResponse[ProviderReviewVoteSummary]
)
def remove_review_vote(
    review_id: int,
    service: ProviderReviewService = Depends(get_provider_review_service),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> ApiResponse[ProviderReviewVoteSummary]:
    return service.remove_review_vote(review_id, current_user)
