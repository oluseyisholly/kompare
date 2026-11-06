from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.enums import FetchRunStatus, ProviderName, ProviderReviewStatus, ProviderReviewType
from app.models.fee import FeeProfile
from app.models.fetch_run import FetchRun
from app.models.giftcard_rate import GiftCardRate
from app.models.giftcard_variant import GiftCardVariant
from app.models.kyc import KycProfile
from app.models.provider import Provider
from app.models.provider_asset import ProviderAsset
from app.models.provider_metric import ProviderMetric
from app.models.provider_review import ProviderReview
from app.models.quote import Quote
from app.repositories.pagination import paginate_query


class ProviderMetricRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_provider_id(self, provider_id: int) -> ProviderMetric | None:
        return (
            self.db.query(ProviderMetric).filter(ProviderMetric.provider_id == provider_id).first()
        )

    def upsert(
        self,
        *,
        provider_id: int,
        average_rating: float | None,
        review_count: int,
        feed_health: str,
        coverage_score: int,
        last_synced_at,
        last_successful_run_at,
        last_failed_run_at,
        last_error_message: str | None,
    ) -> ProviderMetric:
        metric = self.get_by_provider_id(provider_id)
        if metric is None:
            metric = ProviderMetric(provider_id=provider_id)
            self.db.add(metric)

        metric.average_rating = (
            Decimal(str(average_rating)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            if average_rating is not None
            else None
        )
        metric.review_count = review_count
        metric.feed_health = feed_health
        metric.coverage_score = max(0, min(100, coverage_score))
        metric.last_synced_at = last_synced_at
        metric.last_successful_run_at = last_successful_run_at
        metric.last_failed_run_at = last_failed_run_at
        metric.last_error_message = last_error_message

        self.db.commit()
        self.db.refresh(metric)
        return metric

    def get_review_summary(self, provider_id: int) -> tuple[float | None, int]:
        average_rating, review_count = (
            self.db.query(func.avg(ProviderReview.rating), func.count(ProviderReview.id))
            .filter(
                ProviderReview.provider_id == provider_id,
                ProviderReview.status == ProviderReviewStatus.PUBLISHED,
                ProviderReview.review_type == ProviderReviewType.REVIEW,
                ProviderReview.rating.isnot(None),
            )
            .one()
        )
        return float(average_rating) if average_rating is not None else None, int(review_count or 0)

    def count_provider_assets(self, provider: ProviderName) -> int:
        return int(
            self.db.query(func.count(ProviderAsset.id))
            .filter(ProviderAsset.provider == provider, ProviderAsset.is_active.is_(True))
            .scalar()
            or 0
        )

    def count_current_quotes(self, provider: ProviderName) -> int:
        return int(
            self.db.query(func.count(Quote.id))
            .filter(Quote.provider == provider, Quote.superseded_at.is_(None))
            .scalar()
            or 0
        )

    def count_kyc_profiles(self, provider: ProviderName) -> int:
        return int(
            self.db.query(func.count(KycProfile.id))
            .filter(KycProfile.provider == provider)
            .scalar()
            or 0
        )

    def count_fee_profiles(self, provider_id: int) -> int:
        return int(
            self.db.query(func.count(FeeProfile.id))
            .filter(FeeProfile.provider_id == provider_id)
            .scalar()
            or 0
        )

    def count_giftcard_variants(self, provider_id: int) -> int:
        return int(
            self.db.query(func.count(GiftCardVariant.id))
            .filter(GiftCardVariant.provider_id == provider_id, GiftCardVariant.is_active.is_(True))
            .scalar()
            or 0
        )

    def count_current_giftcard_rates(self, provider_id: int) -> int:
        return int(
            self.db.query(func.count(GiftCardRate.id))
            .filter(
                GiftCardRate.provider_id == provider_id,
                GiftCardRate.is_active.is_(True),
                GiftCardRate.superseded_at.is_(None),
            )
            .scalar()
            or 0
        )

    def get_latest_fetch_run(
        self, provider: ProviderName, status: FetchRunStatus | None = None
    ) -> FetchRun | None:
        query = self.db.query(FetchRun).filter(FetchRun.provider == provider)
        if status is not None:
            query = query.filter(FetchRun.status == status)
        return query.order_by(
            FetchRun.finished_at.desc().nullslast(), FetchRun.started_at.desc(), FetchRun.id.desc()
        ).first()

    def list_provider_overview(
        self,
        *,
        page: int,
        per_page: int,
        search: str | None = None,
        category=None,
        is_active: bool | None = None,
    ):
        query = (
            self.db.query(Provider, ProviderMetric)
            .outerjoin(ProviderMetric, ProviderMetric.provider_id == Provider.id)
            .order_by(Provider.name.asc(), Provider.id.asc())
        )

        if search:
            query = query.filter(Provider.name.ilike(f"%{search.strip()}%"))
        if category is not None:
            query = query.filter(Provider.category == category)
        if is_active is not None:
            query = query.filter(Provider.is_active.is_(is_active))

        return paginate_query(query, page=page, per_page=per_page)
