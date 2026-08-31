from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.core.exceptions import BadRequestError, NotFoundError
from app.models.enums import FetchRunStatus, ProviderName
from app.repositories.report import ReportRepository
from app.schemas.common import ApiResponse, PaginatedData, build_paginated_response
from app.schemas.report import (
    ExchangeBuyPreviewReport,
    ExchangeSellPreviewReport,
    ExchangeSpreadReport,
    IngestionHealthReport,
    KycSummaryLevel,
    KycSummaryReport,
    LatestRateReportRow,
    PlatformSummaryReport,
    QuoteTrendPoint,
    QuoteTrendReport,
    RawActivityRow,
)


class ReportService:
    def __init__(self, repository: ReportRepository) -> None:
        self.repository = repository

    def _provider_or_404(self, provider: str) -> ProviderName:
        try:
            return ProviderName(provider.lower())
        except ValueError as exc:
            raise NotFoundError(
                f"Unknown platform: {provider}",
                data={"provider": provider},
            ) from exc

    @staticmethod
    def _compute_spread(buy_rate: Decimal | None, sell_rate: Decimal | None) -> Decimal | None:
        if buy_rate is None or sell_rate is None:
            return None
        return sell_rate - buy_rate

    @staticmethod
    def _compute_spread_percent(buy_rate: Decimal | None, sell_rate: Decimal | None) -> Decimal | None:
        if buy_rate in (None, Decimal("0")) or sell_rate is None:
            return None
        return ((sell_rate - buy_rate) / buy_rate) * Decimal("100")

    @staticmethod
    def _resolve_period(period: str) -> timedelta:
        normalized = period.lower()
        mapping = {
            "24h": timedelta(hours=24),
            "7d": timedelta(days=7),
            "30d": timedelta(days=30),
            "90d": timedelta(days=90),
        }
        if normalized not in mapping:
            raise BadRequestError(
                "Invalid trend period",
                data={"period": period, "allowed_values": list(mapping.keys())},
            )
        return mapping[normalized]

    def get_platform_summary(self, provider: str) -> ApiResponse[PlatformSummaryReport]:
        provider_enum = self._provider_or_404(provider)
        latest_fetch_run = self.repository.get_latest_fetch_run(provider_enum)
        return ApiResponse(
            responseCode=200,
            message="Platform summary retrieved successfully",
            data=PlatformSummaryReport(
                provider=provider_enum.value,
                total_assets=self.repository.count_assets(provider_enum),
                total_quotes=self.repository.count_quotes(provider_enum),
                total_raw_records=self.repository.count_raw_records(provider_enum),
                total_kyc_profiles=self.repository.count_kyc_profiles(provider_enum),
                latest_quote_at=self.repository.get_latest_quote_at(provider_enum),
                latest_kyc_at=self.repository.get_latest_kyc_at(provider_enum),
                latest_fetch_run_id=latest_fetch_run.id if latest_fetch_run else None,
                latest_fetch_run_status=latest_fetch_run.status.value if latest_fetch_run else None,
                latest_fetch_run_started_at=latest_fetch_run.started_at if latest_fetch_run else None,
                latest_fetch_run_finished_at=latest_fetch_run.finished_at if latest_fetch_run else None,
            ),
        )

    def get_latest_rates(self, provider: str, *, page: int, per_page: int) -> ApiResponse[PaginatedData[LatestRateReportRow]]:
        provider_enum = self._provider_or_404(provider)
        rows, total = self.repository.get_latest_rates(provider_enum, page=page, per_page=per_page)
        items = [
            LatestRateReportRow(
                provider_symbol=row.provider_asset.provider_symbol if row.provider_asset else None,
                asset_code=row.asset.code,
                base_currency=row.base_currency,
                quote_currency=row.quote_currency,
                buy_rate=row.buy_rate,
                sell_rate=row.sell_rate,
                mid_rate=row.mid_rate,
                market_price=row.market_price,
                spread=self._compute_spread(row.buy_rate, row.sell_rate),
                spread_percent=self._compute_spread_percent(row.buy_rate, row.sell_rate),
                captured_at=row.captured_at,
            )
            for row in rows
        ]
        return build_paginated_response(
            items=items,
            page=page,
            per_page=per_page,
            total=total,
            message="Latest rates retrieved successfully",
        )

    def get_ingestion_health(self, provider: str) -> ApiResponse[IngestionHealthReport]:
        provider_enum = self._provider_or_404(provider)
        runs = self.repository.get_runs(provider_enum)
        latest_run = runs[0] if runs else None
        last_success = next((run for run in runs if run.status == FetchRunStatus.SUCCESS), None)
        last_failed = next((run for run in runs if run.status == FetchRunStatus.FAILED), None)
        return ApiResponse(
            responseCode=200,
            message="Ingestion health retrieved successfully",
            data=IngestionHealthReport(
                provider=provider_enum.value,
                total_runs=len(runs),
                successful_runs=sum(1 for run in runs if run.status == FetchRunStatus.SUCCESS),
                failed_runs=sum(1 for run in runs if run.status == FetchRunStatus.FAILED),
                last_successful_run_at=last_success.started_at if last_success else None,
                last_failed_run_at=last_failed.started_at if last_failed else None,
                last_error_message=last_failed.error_message if last_failed else None,
                latest_run_status=latest_run.status.value if latest_run else None,
                latest_run_started_at=latest_run.started_at if latest_run else None,
            ),
        )

    def get_kyc_summary(self, provider: str) -> ApiResponse[KycSummaryReport]:
        provider_enum = self._provider_or_404(provider)
        profile = self.repository.get_latest_kyc_profile(provider_enum)
        if profile is None:
            return ApiResponse(
                responseCode=200,
                message="KYC summary retrieved successfully",
                data=KycSummaryReport(
                    provider=provider_enum.value,
                    title=None,
                    source_url=None,
                    source_updated_at=None,
                    fetched_at=None,
                    levels=[],
                ),
            )

        levels = sorted(profile.levels, key=lambda level: level.rank)
        return ApiResponse(
            responseCode=200,
            message="KYC summary retrieved successfully",
            data=KycSummaryReport(
                provider=provider_enum.value,
                title=profile.title,
                source_url=profile.source_url,
                source_updated_at=profile.source_updated_at,
                fetched_at=profile.fetched_at,
                levels=[
                    KycSummaryLevel(
                        level_name=level.level_name,
                        rank=level.rank,
                        limit_reference=level.limit_reference,
                        exchange_limit_text=level.exchange_limit_text,
                        exchange_limit_period=level.exchange_limit_period,
                        fiat_deposit_limit=level.fiat_deposit_limit,
                        fiat_withdrawal_limit=level.fiat_withdrawal_limit,
                        crypto_deposit_limit=level.crypto_deposit_limit,
                        crypto_withdrawal_limit=level.crypto_withdrawal_limit,
                        requirements_count=len(level.requirements or []),
                        notes=level.notes,
                    )
                    for level in levels
                ],
            ),
        )

    def get_raw_activity(self, provider: str) -> ApiResponse[list[RawActivityRow]]:
        provider_enum = self._provider_or_404(provider)
        rows = self.repository.get_raw_activity(provider_enum)
        return ApiResponse(
            responseCode=200,
            message="Raw activity retrieved successfully",
            data=[RawActivityRow(source_type=source_type.value, count=count) for source_type, count in rows],
        )

    def get_exchange_buy_preview(
        self,
        provider: str,
        *,
        base_currency: str,
        quote_currency: str,
        amount_in_quote: Decimal,
    ) -> ApiResponse[ExchangeBuyPreviewReport]:
        provider_enum = self._provider_or_404(provider)
        quote = self.repository.get_latest_quote_for_pair(
            provider_enum,
            base_currency=base_currency.upper(),
            quote_currency=quote_currency.upper(),
        )
        if quote is None or quote.buy_rate in (None, Decimal("0")):
            raise NotFoundError(
                "Buy quote not found for the requested pair",
                data={"provider": provider, "base_currency": base_currency, "quote_currency": quote_currency},
            )

        asset_received = amount_in_quote / quote.buy_rate
        return ApiResponse(
            responseCode=200,
            message="Exchange buy preview retrieved successfully",
            data=ExchangeBuyPreviewReport(
                provider=provider_enum.value,
                provider_symbol=quote.provider_asset.provider_symbol if quote.provider_asset else None,
                base_currency=quote.base_currency,
                quote_currency=quote.quote_currency,
                amount_in_quote=amount_in_quote,
                buy_rate=quote.buy_rate,
                asset_received=asset_received,
                captured_at=quote.captured_at,
            ),
        )

    def get_exchange_sell_preview(
        self,
        provider: str,
        *,
        base_currency: str,
        quote_currency: str,
        amount_in_base: Decimal,
    ) -> ApiResponse[ExchangeSellPreviewReport]:
        provider_enum = self._provider_or_404(provider)
        quote = self.repository.get_latest_quote_for_pair(
            provider_enum,
            base_currency=base_currency.upper(),
            quote_currency=quote_currency.upper(),
        )
        if quote is None or quote.sell_rate is None:
            raise NotFoundError(
                "Sell quote not found for the requested pair",
                data={"provider": provider, "base_currency": base_currency, "quote_currency": quote_currency},
            )

        quote_received = amount_in_base * quote.sell_rate
        return ApiResponse(
            responseCode=200,
            message="Exchange sell preview retrieved successfully",
            data=ExchangeSellPreviewReport(
                provider=provider_enum.value,
                provider_symbol=quote.provider_asset.provider_symbol if quote.provider_asset else None,
                base_currency=quote.base_currency,
                quote_currency=quote.quote_currency,
                amount_in_base=amount_in_base,
                sell_rate=quote.sell_rate,
                quote_received=quote_received,
                captured_at=quote.captured_at,
            ),
        )

    def get_exchange_spread(
        self,
        provider: str,
        *,
        base_currency: str,
        quote_currency: str,
    ) -> ApiResponse[ExchangeSpreadReport]:
        provider_enum = self._provider_or_404(provider)
        quote = self.repository.get_latest_quote_for_pair(
            provider_enum,
            base_currency=base_currency.upper(),
            quote_currency=quote_currency.upper(),
        )
        if quote is None:
            raise NotFoundError(
                "Quote not found for the requested pair",
                data={"provider": provider, "base_currency": base_currency, "quote_currency": quote_currency},
            )

        return ApiResponse(
            responseCode=200,
            message="Exchange spread retrieved successfully",
            data=ExchangeSpreadReport(
                provider=provider_enum.value,
                provider_symbol=quote.provider_asset.provider_symbol if quote.provider_asset else None,
                base_currency=quote.base_currency,
                quote_currency=quote.quote_currency,
                buy_rate=quote.buy_rate,
                sell_rate=quote.sell_rate,
                mid_rate=quote.mid_rate,
                spread=self._compute_spread(quote.buy_rate, quote.sell_rate),
                spread_percent=self._compute_spread_percent(quote.buy_rate, quote.sell_rate),
                captured_at=quote.captured_at,
            ),
        )

    def get_quote_trend(
        self,
        provider: str,
        *,
        base_currency: str,
        quote_currency: str,
        period: str,
    ) -> ApiResponse[QuoteTrendReport]:
        provider_enum = self._provider_or_404(provider)
        duration = self._resolve_period(period)
        ended_at = datetime.now(UTC)
        started_at = ended_at - duration
        rows = self.repository.get_quote_trend(
            provider_enum,
            base_currency=base_currency.upper(),
            quote_currency=quote_currency.upper(),
            started_at=started_at,
            ended_at=ended_at,
        )
        if not rows:
            raise NotFoundError(
                "No quote trend data found for the requested pair and period",
                data={
                    "provider": provider,
                    "base_currency": base_currency,
                    "quote_currency": quote_currency,
                    "period": period,
                },
            )

        latest = rows[-1]
        return ApiResponse(
            responseCode=200,
            message="Quote trend retrieved successfully",
            data=QuoteTrendReport(
                provider=provider_enum.value,
                provider_symbol=latest.provider_asset.provider_symbol if latest.provider_asset else None,
                base_currency=base_currency.upper(),
                quote_currency=quote_currency.upper(),
                period=period.lower(),
                points_count=len(rows),
                started_at=started_at,
                ended_at=ended_at,
                points=[
                    QuoteTrendPoint(
                        captured_at=row.captured_at,
                        buy_rate=row.buy_rate,
                        sell_rate=row.sell_rate,
                        mid_rate=row.mid_rate,
                        market_price=row.market_price,
                    )
                    for row in rows
                ],
            ),
        )
