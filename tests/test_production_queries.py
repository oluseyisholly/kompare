from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import event
from test_stanbic_ingestion import db as existing_database

from app.models.asset import Asset
from app.models.enums import (
    FetchRunStatus,
    MarketCategory,
    ProviderName,
    ProviderReviewStatus,
    ProviderReviewType,
)
from app.models.fetch_run import FetchRun
from app.models.giftcard_variant import GiftCardVariant
from app.models.provider import Provider
from app.models.provider_review import ProviderReview
from app.repositories.report import ReportRepository

db = existing_database


def test_listing_query_counts_do_not_grow_per_item(db):
    from app.core.database import get_db
    from app.main import app

    provider = Provider(slug="tbay", name="Tbay fixture", category=MarketCategory.GIFTCARD)
    asset = Asset(code="TESTCARD", name="Test card", category=MarketCategory.GIFTCARD)
    db.add_all([provider, asset])
    db.flush()
    db.add_all(
        [
            GiftCardVariant(
                provider_id=provider.id, asset_id=asset.id, external_id=str(n), name=f"Card {n}"
            )
            for n in range(5)
        ]
    )
    db.add_all(
        [
            ProviderReview(
                provider_id=provider.id,
                review_type=ProviderReviewType.REVIEW,
                status=ProviderReviewStatus.PUBLISHED,
                rating=4,
                title="Fixture title",
                body="Fixture review",
            )
            for _ in range(5)
        ]
    )
    db.commit()
    old = app.dependency_overrides.copy()
    app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)
    try:
        for endpoint in ["/providers/tbay/giftcards/variants", "/providers/tbay/reviews"]:
            counts = []
            for size in [1, 5]:
                queries = []

                def record(connection, cursor, statement, parameters, context, executemany):
                    if statement.lstrip().upper().startswith("SELECT"):
                        queries.append(statement)

                event.listen(db.bind, "before_cursor_execute", record)
                try:
                    response = client.get(endpoint, params={"per_page": size})
                finally:
                    event.remove(db.bind, "before_cursor_execute", record)
                assert response.status_code == 200, response.text
                counts.append(len(queries))
            assert counts[0] == counts[1], (endpoint, counts)
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(old)


def test_health_is_sql_aggregated_and_does_not_load_raw_metadata(db):
    now = datetime.now(UTC)
    for n, status in enumerate(
        [FetchRunStatus.SUCCESS, FetchRunStatus.FAILED, FetchRunStatus.SUCCESS]
    ):
        db.add(
            FetchRun(
                provider=ProviderName.WISE,
                status=status,
                started_at=now + timedelta(seconds=n),
                metadata_json={"large_payload": "x" * 1000},
                error_message="fixture error" if n == 1 else None,
            )
        )
    db.commit()
    queries = []

    def record(connection, cursor, statement, parameters, context, executemany):
        queries.append(statement)

    event.listen(db.bind, "before_cursor_execute", record)
    try:
        result = ReportRepository(db).ingestion_health(ProviderName.WISE)
    finally:
        event.remove(db.bind, "before_cursor_execute", record)
    assert (
        result["total_runs"] == 3 and result["successful_runs"] == 2 and result["failed_runs"] == 1
    )
    assert result["last_error_message"] == "fixture error"
    assert result["latest_run_status"] == "success"
    assert len(queries) == 3 and not any("metadata_json" in sql for sql in queries)


def test_batch_review_engagement_preserves_counts_and_moderation(db):
    from app.models.enums import UserRole
    from app.models.provider_review import ProviderReviewComment, ProviderReviewVote
    from app.models.user import User
    from app.repositories.provider_review import ProviderReviewRepository

    provider = Provider(slug="tbay", name="Tbay", category=MarketCategory.GIFTCARD)
    voters = [
        User(email=f"voter-{n}@example.invalid", password_hash="fixture", role=UserRole.USER)
        for n in range(2)
    ]
    db.add_all([provider, *voters])
    db.flush()
    review = ProviderReview(
        provider_id=provider.id,
        review_type=ProviderReviewType.REVIEW,
        status=ProviderReviewStatus.PUBLISHED,
        rating=5,
        title="Fixture",
        body="Fixture",
    )
    db.add(review)
    db.flush()
    db.add_all(
        [
            ProviderReviewVote(review_id=review.id, user_id=voters[0].id, is_helpful=True),
            ProviderReviewVote(review_id=review.id, user_id=voters[1].id, is_helpful=False),
        ]
    )
    db.add_all(
        [
            ProviderReviewComment(review_id=review.id, body="Fixture", status=status)
            for status in [
                ProviderReviewStatus.PUBLISHED,
                ProviderReviewStatus.PUBLISHED,
                ProviderReviewStatus.PENDING,
            ]
        ]
    )
    db.commit()
    assert ProviderReviewRepository(db).engagement_counts([review.id])[review.id] == {
        "helpful": 1,
        "not_helpful": 1,
        "comments": 2,
    }


def test_batch_latest_giftcard_rate_keeps_latest_current_version(db):
    from app.models.giftcard_rate import GiftCardRate
    from app.repositories.giftcard_rate import GiftCardRateRepository

    provider = Provider(slug="tbay", name="Tbay", category=MarketCategory.GIFTCARD)
    asset = Asset(code="CARD", name="Card", category=MarketCategory.GIFTCARD)
    db.add_all([provider, asset])
    db.flush()
    variant = GiftCardVariant(
        provider_id=provider.id, asset_id=asset.id, external_id="fixture", name="Fixture"
    )
    db.add(variant)
    db.flush()
    now = datetime.now(UTC)
    old = GiftCardRate(
        provider_id=provider.id,
        giftcard_variant_id=variant.id,
        rate_value=100,
        captured_at=now - timedelta(days=1),
        superseded_at=now,
    )
    current = GiftCardRate(
        provider_id=provider.id, giftcard_variant_id=variant.id, rate_value=200, captured_at=now
    )
    db.add_all([old, current])
    db.commit()
    assert (
        GiftCardRateRepository(db).get_latest_for_variants([variant.id])[variant.id].id
        == current.id
    )
