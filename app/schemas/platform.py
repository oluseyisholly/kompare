from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict


class PlatformAssetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    provider_symbol: str
    provider_name: str | None
    asset_code: str
    asset_name: str
    quote_unit: str | None
    is_active: bool
    metadata_json: dict[str, Any] | None


class PlatformQuoteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    provider_symbol: str | None
    asset_code: str
    base_currency: str
    quote_currency: str
    quote_type: str
    buy_rate: Decimal | None
    sell_rate: Decimal | None
    mid_rate: Decimal | None
    market_price: Decimal | None
    captured_at: datetime


class FetchRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    provider: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    error_message: str | None
    records_fetched: int
    metadata_json: dict[str, Any] | None


class RawRecordRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    provider: str
    fetch_run_id: int
    source_type: str
    source_url: str | None
    external_id: str | None
    payload: dict[str, Any] | None
    raw_text: str | None
    fetched_at: datetime


class KycLevelRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    level_name: str
    rank: int
    description: str | None
    limit_reference: str | None
    exchange_limit_text: str | None
    exchange_limit_period: str | None
    fiat_deposit_limit: str | None
    fiat_withdrawal_limit: str | None
    crypto_deposit_limit: str | None
    crypto_withdrawal_limit: str | None
    requirements: list[str] | None
    notes: str | None
    metadata_json: dict[str, Any] | None


class KycProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    provider: str
    title: str
    source_url: str
    source_updated_at: datetime | None
    fetched_at: datetime
    levels: list[KycLevelRead]


class KycLevelCreate(BaseModel):
    level_name: str
    rank: int
    description: str | None = None
    limit_reference: str | None = None
    exchange_limit_text: str | None = None
    exchange_limit_period: str | None = None
    fiat_deposit_limit: str | None = None
    fiat_withdrawal_limit: str | None = None
    crypto_deposit_limit: str | None = None
    crypto_withdrawal_limit: str | None = None
    requirements: list[str] | None = None
    notes: str | None = None
    metadata_json: dict[str, Any] | None = None


class KycProfileCreate(BaseModel):
    title: str
    source_url: str
    source_updated_at: datetime | None = None
    fetched_at: datetime | None = None
    levels: list[KycLevelCreate]
