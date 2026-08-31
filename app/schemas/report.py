from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class PlatformSummaryReport(BaseModel):
    provider: str
    total_assets: int
    total_quotes: int
    total_raw_records: int
    total_kyc_profiles: int
    latest_quote_at: datetime | None
    latest_kyc_at: datetime | None
    latest_fetch_run_id: int | None
    latest_fetch_run_status: str | None
    latest_fetch_run_started_at: datetime | None
    latest_fetch_run_finished_at: datetime | None


class LatestRateReportRow(BaseModel):
    provider_symbol: str | None
    asset_code: str
    base_currency: str
    quote_currency: str
    buy_rate: Decimal | None
    sell_rate: Decimal | None
    mid_rate: Decimal | None
    market_price: Decimal | None
    spread: Decimal | None
    spread_percent: Decimal | None
    captured_at: datetime


class IngestionHealthReport(BaseModel):
    provider: str
    total_runs: int
    successful_runs: int
    failed_runs: int
    last_successful_run_at: datetime | None
    last_failed_run_at: datetime | None
    last_error_message: str | None
    latest_run_status: str | None
    latest_run_started_at: datetime | None


class KycSummaryLevel(BaseModel):
    level_name: str
    rank: int
    limit_reference: str | None
    exchange_limit_text: str | None
    exchange_limit_period: str | None
    fiat_deposit_limit: str | None
    fiat_withdrawal_limit: str | None
    crypto_deposit_limit: str | None
    crypto_withdrawal_limit: str | None
    requirements_count: int
    notes: str | None


class KycSummaryReport(BaseModel):
    provider: str
    title: str | None
    source_url: str | None
    source_updated_at: datetime | None
    fetched_at: datetime | None
    levels: list[KycSummaryLevel]


class RawActivityRow(BaseModel):
    source_type: str
    count: int


class ExchangeBuyPreviewReport(BaseModel):
    provider: str
    provider_symbol: str | None
    base_currency: str
    quote_currency: str
    amount_in_quote: Decimal
    buy_rate: Decimal
    asset_received: Decimal
    captured_at: datetime


class ExchangeSellPreviewReport(BaseModel):
    provider: str
    provider_symbol: str | None
    base_currency: str
    quote_currency: str
    amount_in_base: Decimal
    sell_rate: Decimal
    quote_received: Decimal
    captured_at: datetime


class ExchangeSpreadReport(BaseModel):
    provider: str
    provider_symbol: str | None
    base_currency: str
    quote_currency: str
    buy_rate: Decimal | None
    sell_rate: Decimal | None
    mid_rate: Decimal | None
    spread: Decimal | None
    spread_percent: Decimal | None
    captured_at: datetime
