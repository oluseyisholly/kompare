from fastapi import APIRouter, Depends, Query
from app.dependencies import get_report_service
from app.schemas.common import ApiResponse, PaginatedData
from app.schemas.report import (
    ExchangeBuyPreviewReport,
    ExchangeSellPreviewReport,
    ExchangeSpreadReport,
    GiftCardSellPreviewReport,
    IngestionHealthReport,
    KycSummaryReport,
    LatestRateReportRow,
    PlatformSummaryReport,
    QuoteTrendReport,
    RawActivityRow,
)
from app.services.report import ReportService

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/providers/{provider}/summary", response_model=ApiResponse[PlatformSummaryReport])
def get_platform_summary(
    provider: str,
    service: ReportService = Depends(get_report_service),
) -> ApiResponse[PlatformSummaryReport]:
    return service.get_platform_summary(provider)


@router.get("/providers/{provider}/crypto/latest-rates", response_model=ApiResponse[PaginatedData[LatestRateReportRow]])
def get_crypto_latest_rates(
    provider: str,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    service: ReportService = Depends(get_report_service),
) -> ApiResponse[PaginatedData[LatestRateReportRow]]:
    return service.get_latest_rates(provider, page=page, per_page=per_page)


@router.get("/providers/{provider}/ingestion-health", response_model=ApiResponse[IngestionHealthReport])
def get_ingestion_health(
    provider: str,
    service: ReportService = Depends(get_report_service),
) -> ApiResponse[IngestionHealthReport]:
    return service.get_ingestion_health(provider)


@router.get("/providers/{provider}/kyc-summary", response_model=ApiResponse[KycSummaryReport])
def get_kyc_summary(
    provider: str,
    service: ReportService = Depends(get_report_service),
) -> ApiResponse[KycSummaryReport]:
    return service.get_kyc_summary(provider)


@router.get("/providers/{provider}/raw-activity", response_model=ApiResponse[list[RawActivityRow]])
def get_raw_activity(
    provider: str,
    service: ReportService = Depends(get_report_service),
) -> ApiResponse[list[RawActivityRow]]:
    return service.get_raw_activity(provider)


@router.get("/providers/{provider}/crypto/exchange/buy-preview", response_model=ApiResponse[ExchangeBuyPreviewReport])
def get_crypto_exchange_buy_preview(
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


@router.get("/providers/{provider}/crypto/exchange/sell-preview", response_model=ApiResponse[ExchangeSellPreviewReport])
def get_crypto_exchange_sell_preview(
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


@router.get("/providers/{provider}/crypto/exchange/spread", response_model=ApiResponse[ExchangeSpreadReport])
def get_crypto_exchange_spread(
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


@router.get("/providers/{provider}/crypto/quotes/trend", response_model=ApiResponse[QuoteTrendReport])
def get_crypto_quote_trend(
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


@router.get("/providers/{provider}/giftcards/sell-preview", response_model=ApiResponse[GiftCardSellPreviewReport])
def get_giftcard_sell_preview(
    provider: str,
    asset_code: str | None = Query(default=None, min_length=1),
    rate_id: int | None = Query(default=None, ge=1),
    source_currency: str | None = Query(default=None, min_length=1),
    face_value: float = Query(..., gt=0),
    region: str | None = Query(default=None),
    card_type: str | None = Query(default=None),
    service: ReportService = Depends(get_report_service),
) -> ApiResponse[GiftCardSellPreviewReport]:
    from decimal import Decimal

    return service.get_giftcard_sell_preview(
        provider,
        asset_code=asset_code,
        rate_id=rate_id,
        source_currency=source_currency,
        face_value=Decimal(str(face_value)),
        region=region,
        card_type=card_type,
    )
