from fastapi import APIRouter, Depends, Query
from app.dependencies import get_report_service
from app.schemas.common import ApiResponse, PaginatedData
from app.schemas.report import (
    ExchangeBuyPreviewReport,
    ExchangeSellPreviewReport,
    ExchangeSpreadReport,
    IngestionHealthReport,
    KycSummaryReport,
    LatestRateReportRow,
    PlatformSummaryReport,
    QuoteTrendReport,
    RawActivityRow,
)
from app.services.report import ReportService

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/platforms/{provider}/summary", response_model=ApiResponse[PlatformSummaryReport])
def get_platform_summary(
    provider: str,
    service: ReportService = Depends(get_report_service),
) -> ApiResponse[PlatformSummaryReport]:
    return service.get_platform_summary(provider)


@router.get("/platforms/{provider}/latest-rates", response_model=ApiResponse[PaginatedData[LatestRateReportRow]])
def get_latest_rates(
    provider: str,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    service: ReportService = Depends(get_report_service),
) -> ApiResponse[PaginatedData[LatestRateReportRow]]:
    return service.get_latest_rates(provider, page=page, per_page=per_page)


@router.get("/platforms/{provider}/ingestion-health", response_model=ApiResponse[IngestionHealthReport])
def get_ingestion_health(
    provider: str,
    service: ReportService = Depends(get_report_service),
) -> ApiResponse[IngestionHealthReport]:
    return service.get_ingestion_health(provider)


@router.get("/platforms/{provider}/kyc-summary", response_model=ApiResponse[KycSummaryReport])
def get_kyc_summary(
    provider: str,
    service: ReportService = Depends(get_report_service),
) -> ApiResponse[KycSummaryReport]:
    return service.get_kyc_summary(provider)


@router.get("/platforms/{provider}/raw-activity", response_model=ApiResponse[list[RawActivityRow]])
def get_raw_activity(
    provider: str,
    service: ReportService = Depends(get_report_service),
) -> ApiResponse[list[RawActivityRow]]:
    return service.get_raw_activity(provider)


@router.get("/platforms/{provider}/exchange/buy-preview", response_model=ApiResponse[ExchangeBuyPreviewReport])
def get_exchange_buy_preview(
    provider: str,
    base_currency: str = Query(..., min_length=1),
    quote_currency: str = Query(..., min_length=1),
    amount_in_quote: float = Query(..., gt=0),
    service: ReportService = Depends(get_report_service),
) -> ApiResponse[ExchangeBuyPreviewReport]:
    from decimal import Decimal

    return service.get_exchange_buy_preview(
        provider,
        base_currency=base_currency,
        quote_currency=quote_currency,
        amount_in_quote=Decimal(str(amount_in_quote)),
    )


@router.get("/platforms/{provider}/exchange/sell-preview", response_model=ApiResponse[ExchangeSellPreviewReport])
def get_exchange_sell_preview(
    provider: str,
    base_currency: str = Query(..., min_length=1),
    quote_currency: str = Query(..., min_length=1),
    amount_in_base: float = Query(..., gt=0),
    service: ReportService = Depends(get_report_service),
) -> ApiResponse[ExchangeSellPreviewReport]:
    from decimal import Decimal

    return service.get_exchange_sell_preview(
        provider,
        base_currency=base_currency,
        quote_currency=quote_currency,
        amount_in_base=Decimal(str(amount_in_base)),
    )


@router.get("/platforms/{provider}/exchange/spread", response_model=ApiResponse[ExchangeSpreadReport])
def get_exchange_spread(
    provider: str,
    base_currency: str = Query(..., min_length=1),
    quote_currency: str = Query(..., min_length=1),
    service: ReportService = Depends(get_report_service),
) -> ApiResponse[ExchangeSpreadReport]:
    return service.get_exchange_spread(
        provider,
        base_currency=base_currency,
        quote_currency=quote_currency,
    )


@router.get("/platforms/{provider}/quotes/trend", response_model=ApiResponse[QuoteTrendReport])
def get_quote_trend(
    provider: str,
    base_currency: str = Query(..., min_length=1),
    quote_currency: str = Query(..., min_length=1),
    period: str = Query(..., pattern="^(24h|7d|30d|90d)$"),
    service: ReportService = Depends(get_report_service),
) -> ApiResponse[QuoteTrendReport]:
    return service.get_quote_trend(
        provider,
        base_currency=base_currency,
        quote_currency=quote_currency,
        period=period,
    )
