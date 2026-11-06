from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ParsedFund(BaseModel):
    code: str = Field(min_length=1)
    name: str = Field(min_length=1)
    fund_type: str
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    bid_price: Decimal | None = Field(default=None, ge=0, max_digits=24, decimal_places=8)
    offer_price: Decimal | None = Field(default=None, ge=0, max_digits=24, decimal_places=8)
    nav_per_unit: Decimal | None = Field(default=None, ge=0, max_digits=24, decimal_places=8)
    yield_percent: Decimal | None = Field(default=None, max_digits=24, decimal_places=8)
    ytd_return_percent: Decimal | None = Field(default=None, max_digits=24, decimal_places=8)
    yield_label: str | None = None
    valuation_date: date | None = None

    @model_validator(mode="after")
    def require_published_value(self):
        if all(
            value is None
            for value in (
                self.bid_price,
                self.offer_price,
                self.nav_per_unit,
                self.yield_percent,
                self.ytd_return_percent,
            )
        ):
            raise ValueError("No published price, yield or return extracted")
        if self.yield_percent is not None and not self.yield_label:
            raise ValueError("Published yield requires its label")
        return self


class PublishedFundMetricRead(BaseModel):
    label: str
    raw_value: str
    value: Decimal | None = Field(default=None, max_digits=24, decimal_places=8)
    unit: str
    mapped_field: str | None = None
    interpretation: Literal["normalized", "unresolved_yield_or_daily_return"]
    status: Literal["available", "not_published", "invalid"]


class MutualFundSnapshotRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    fund_id: int
    bid_price: Decimal | None
    offer_price: Decimal | None
    nav_per_unit: Decimal | None
    yield_percent: Decimal | None
    ytd_return_percent: Decimal | None = None
    yield_label: str | None
    valuation_date: date | None
    captured_at: datetime
    fetch_run_id: int
    raw_record_id: int
    source_url: str | None = None
    published_metrics: list[PublishedFundMetricRead] = Field(default_factory=list)


class MutualFundRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    provider_id: int
    code: str
    name: str
    fund_type: str
    currency: str
    minimum_initial_investment: Decimal | None = None
    minimum_topup: Decimal | None = None
    minimum_holding_days: int | None = None
    risk_label: str | None = None
    management_fee_percent_pa: Decimal | None = None
    distribution_frequency: str | None = None
    structure: str | None = None
    details_metadata: dict | None = None
    latest_snapshot: MutualFundSnapshotRead | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ParsedFundDetails(BaseModel):
    """Only fields actually observed are set; absent fields must never clear storage."""

    model_config = ConfigDict(extra="forbid")
    code: str = Field(pattern=r"^(?:stanbic-[a-z0-9]+|united-capital-[a-z0-9]+(?:-[a-z0-9]+)*)$")
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    minimum_initial_investment: Decimal | None = Field(
        default=None, ge=0, max_digits=24, decimal_places=8
    )
    minimum_topup: Decimal | None = Field(default=None, ge=0, max_digits=24, decimal_places=8)
    minimum_holding_days: int | None = Field(default=None, ge=0, strict=True)
    risk_label: str | None = Field(default=None, min_length=1)
    management_fee_percent_pa: Decimal | None = Field(
        default=None, ge=0, max_digits=24, decimal_places=8
    )
    distribution_frequency: str | None = Field(default=None, min_length=1)
    structure: str | None = Field(default=None, pattern=r"^(open_ended|closed_ended)$")
