from __future__ import annotations

from app.models.enums import FetchRunStatus, MarketCategory, ProviderName
from app.models.provider import Provider
from app.models.provider_metric import ProviderMetric
from app.repositories.provider import ProviderRepository
from app.repositories.provider_metric import ProviderMetricRepository
from app.services.provider_metrics.scoring import CoverageSignal, calculate_coverage_score


class ProviderMetricService:
    def __init__(
        self,
        *,
        repository: ProviderMetricRepository,
        provider_repository: ProviderRepository,
    ) -> None:
        self.repository = repository
        self.provider_repository = provider_repository

    def refresh_provider(self, provider: Provider) -> ProviderMetric:
        provider_enum = self._provider_enum(provider.slug)
        average_rating, review_count = self.repository.get_review_summary(provider.id)
        signals: set[CoverageSignal] = set()

        latest_run = None
        latest_success = None
        latest_failure = None
        last_error_message = None

        if provider_enum is not None:
            latest_run = self.repository.get_latest_fetch_run(provider_enum)
            latest_success = self.repository.get_latest_fetch_run(
                provider_enum, FetchRunStatus.SUCCESS
            )
            latest_failure = self.repository.get_latest_fetch_run(
                provider_enum, FetchRunStatus.FAILED
            )
            last_error_message = (
                latest_failure.error_message if latest_failure is not None else None
            )

            if self.repository.count_kyc_profiles(provider_enum) > 0:
                signals.add(CoverageSignal.KYC)
            if latest_success is not None:
                signals.add(CoverageSignal.RECENT_SUCCESSFUL_RUN)

        if provider.category == MarketCategory.CRYPTO and provider_enum is not None:
            if self.repository.count_provider_assets(provider_enum) > 0:
                signals.add(CoverageSignal.ASSETS)
            if self.repository.count_current_quotes(provider_enum) > 0:
                signals.add(CoverageSignal.QUOTES)
            if self.repository.count_fee_profiles(provider.id) > 0:
                signals.add(CoverageSignal.FEES)

        if provider.category == MarketCategory.GIFTCARD:
            if self.repository.count_giftcard_variants(provider.id) > 0:
                signals.add(CoverageSignal.GIFT_CARD_VARIANTS)
            if self.repository.count_current_giftcard_rates(provider.id) > 0:
                signals.add(CoverageSignal.GIFT_CARD_RATES)

        if (
            provider.category in {MarketCategory.FX, MarketCategory.MUTUAL_FUND}
            and provider_enum is not None
        ):
            if self.repository.count_current_quotes(provider_enum) > 0:
                signals.add(CoverageSignal.QUOTES)

        coverage_score = calculate_coverage_score(provider.category, signals)
        feed_health = self._feed_health(latest_run, latest_success)

        return self.repository.upsert(
            provider_id=provider.id,
            average_rating=average_rating,
            review_count=review_count,
            feed_health=feed_health,
            coverage_score=coverage_score,
            last_synced_at=latest_success.finished_at if latest_success is not None else None,
            last_successful_run_at=latest_success.finished_at
            if latest_success is not None
            else None,
            last_failed_run_at=latest_failure.finished_at if latest_failure is not None else None,
            last_error_message=last_error_message,
        )

    def refresh_provider_by_slug(self, slug: str) -> ProviderMetric | None:
        provider = self.provider_repository.get_by_slug(slug)
        if provider is None:
            return None
        return self.refresh_provider(provider)

    def refresh_all_providers(self) -> list[ProviderMetric]:
        return [self.refresh_provider(provider) for provider in self.provider_repository.list_all()]

    def list_provider_overview(
        self,
        *,
        page: int,
        per_page: int,
        search: str | None = None,
        category=None,
        is_active: bool | None = None,
    ):
        return self.repository.list_provider_overview(
            page=page,
            per_page=per_page,
            search=search,
            category=category,
            is_active=is_active,
        )

    @staticmethod
    def _provider_enum(slug: str) -> ProviderName | None:
        try:
            return ProviderName(slug.lower())
        except ValueError:
            return None

    @staticmethod
    def _feed_health(latest_run, latest_success) -> str:
        if latest_run is None:
            return "unknown"
        if latest_run.status == FetchRunStatus.PENDING:
            return "syncing"
        if latest_run.status == FetchRunStatus.FAILED:
            return "unhealthy"
        if latest_success is not None:
            return "healthy"
        return "unknown"
