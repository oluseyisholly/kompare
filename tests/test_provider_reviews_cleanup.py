"""Keep review documentation together and provider rating calculations consistent."""

import pytest
from sqlalchemy import event
from test_stanbic_ingestion import db as existing_database

from app.main import app
from app.models.enums import (
    MarketCategory,
    ProviderReviewStatus,
    ProviderReviewType,
    ProviderTipCategory,
    ProviderTipSeverity,
)
from app.models.provider import Provider
from app.models.provider_review import ProviderReview
from app.repositories.provider_metric import ProviderMetricRepository
from app.repositories.provider_review import ProviderReviewRepository
from app.routers.provider_review import router as reviews_router

db = existing_database


def test_all_review_routes_share_one_documentation_group():
    schema = app.openapi()
    for route in reviews_router.routes:
        for method in route.methods:
            assert schema["paths"][route.path][method.lower()]["tags"] == ["Provider Reviews"]
    for path, method in (
        ("/providers/", "get"),
        ("/providers/overview", "get"),
        ("/providers/{slug}", "get"),
        ("/providers/{slug}", "patch"),
    ):
        assert schema["paths"][path][method]["tags"] == ["Providers"]
    assert sum(tag["name"] == "Provider Reviews" for tag in schema["tags"]) == 1
    assert not any(
        "provider-reviews" in operation.get("tags", [])
        for operations in schema["paths"].values()
        for operation in operations.values()
    )


def test_shared_rating_calculation_filters_moderation_tips_and_other_providers(db):
    provider = Provider(slug="quidax", name="Quidax", category=MarketCategory.CRYPTO)
    other = Provider(slug="busha", name="Busha", category=MarketCategory.CRYPTO)
    db.add_all([provider, other])
    db.flush()
    rows = [
        ProviderReview(
            provider_id=provider.id,
            review_type=ProviderReviewType.REVIEW,
            status=ProviderReviewStatus.PUBLISHED,
            rating=rating,
            title="Review",
            body="Review",
        )
        for rating in (1, 4, 5)
    ]
    db.add_all(
        rows
        + [
            ProviderReview(
                provider_id=provider.id,
                review_type=ProviderReviewType.REVIEW,
                status=status,
                rating=1,
                title="Review",
                body="Review",
            )
            for status in (ProviderReviewStatus.PENDING, ProviderReviewStatus.HIDDEN)
        ]
        + [
            ProviderReview(
                provider_id=other.id,
                review_type=ProviderReviewType.REVIEW,
                status=ProviderReviewStatus.PUBLISHED,
                rating=5,
                title="Other",
                body="Other",
            ),
            ProviderReview(
                provider_id=provider.id,
                review_type=ProviderReviewType.TIP,
                status=ProviderReviewStatus.PUBLISHED,
                body="Tip",
                tip_category=ProviderTipCategory.GENERAL_TIP,
                tip_severity=ProviderTipSeverity.LOW,
            ),
        ]
    )
    db.commit()
    provider_id = provider.id
    reviews, metrics = ProviderReviewRepository(db), ProviderMetricRepository(db)
    queries = []

    def record(connection, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            queries.append(statement)

    event.listen(db.bind, "before_cursor_execute", record)
    try:
        average, count = metrics.get_review_summary(provider_id)
        assert average == pytest.approx(10 / 3) and count == 3
        assert len(queries) == 1  # Metrics do not fetch an unnecessary rating histogram.
        summary = reviews.get_summary_by_provider(provider_id)
        assert summary == (average, count, {1: 1, 4: 1, 5: 1})
        assert len(queries) == 3
    finally:
        event.remove(db.bind, "before_cursor_execute", record)

    rows[-1].status = ProviderReviewStatus.HIDDEN
    db.commit()
    assert metrics.get_review_summary(provider_id) == (2.5, 2)
    assert reviews.get_summary_by_provider(provider_id) == (2.5, 2, {1: 1, 4: 1})


def test_empty_ratings_remain_null_in_both_consumers(db):
    provider = Provider(slug="wise", name="Wise", category=MarketCategory.FX)
    db.add(provider)
    db.commit()
    assert ProviderMetricRepository(db).get_review_summary(provider.id) == (None, 0)
    assert ProviderReviewRepository(db).get_summary_by_provider(provider.id) == (None, 0, {})
