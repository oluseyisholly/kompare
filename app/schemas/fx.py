from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StrictBool,
    StringConstraints,
    model_validator,
)
from pydantic_core import PydanticCustomError

from app.models.enums import ProviderName

Currency = Annotated[
    str,
    StringConstraints(pattern=r"^[A-Z]{3}$"),
    BeforeValidator(lambda value: value.strip().upper() if isinstance(value, str) else value),
]


def require_positive_amount(value):
    if value <= 0:
        raise PydanticCustomError("fx_positive_amount", "Amount must be greater than zero")
    return value


Amount = Annotated[
    Decimal,
    Field(
        max_digits=24,
        decimal_places=8,
        allow_inf_nan=False,
        json_schema_extra={"exclusiveMinimum": 0},
    ),
    AfterValidator(require_positive_amount),
]
Nonnegative = Annotated[Decimal, Field(ge=0, allow_inf_nan=False)]
Positive = Annotated[Decimal, Field(gt=0, allow_inf_nan=False)]


class FxConversionRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "provider": provider.value,
                    "source_currency": "USD",
                    "target_currency": "NGN",
                    "source_amount": "100.00",
                }
                for provider in (ProviderName.WISE, ProviderName.FLUTTERWAVE, ProviderName.FINCRA)
            ],
        },
    )

    provider: ProviderName = Field(
        description="ProviderName enum value. The provider must be active and support FX; "
        "Wise, Flutterwave and Fincra are implemented FX providers.",
        examples=[ProviderName.WISE.value],
    )
    source_currency: Currency = Field(description="Currency the customer gives.", examples=["USD"])
    target_currency: Currency = Field(
        description="Currency the customer receives.", examples=["NGN"]
    )
    source_amount: Amount = Field(
        description="Positive source-currency amount, preferably supplied as a decimal string.",
        examples=["100.00"],
    )

    @model_validator(mode="after")
    def different_currencies(self):
        if self.source_currency == self.target_currency:
            raise PydanticCustomError(
                "fx_currency_pair", "Source and target currencies must differ"
            )
        return self


class FxConversionRead(BaseModel):
    provider: str
    source_currency: Currency
    target_currency: Currency
    source_amount: Decimal
    reference_rate: Positive | None
    applied_rate: Positive
    rate_classification: Literal["reference_rate", "transfer_rate_observation", "treasury_rate"] = (
        "reference_rate"
    )
    rate_direction: Literal["target_per_source"] = "target_per_source"
    sampled_destination_amount: Decimal | None = None
    sample_source_amount: Decimal | None = None
    sample_target_amount: Decimal | None = None
    sample_selection_policy: str | None = None
    freshness_basis: Literal["provider_timestamp", "collection_timestamp"] = "provider_timestamp"
    gross_target_amount: Decimal
    unrounded_gross_target_amount: Decimal
    target_decimal_places: int | None
    rounding_policy: str
    precision_source: str | None
    fee_status: Literal["unavailable"] = "unavailable"
    fee_amount: Decimal | None = None
    fee_currency: Currency | None = None
    net_target_amount: Decimal | None = None
    estimated_net_target_amount: Decimal | None = Field(
        default=None, deprecated=True, description="Legacy alias for net_target_amount."
    )
    observed_at: datetime = Field(description="Time this stored rate was last observed.")
    provider_rate_timestamp: datetime | None
    expires_at: datetime | None = None
    captured_at: datetime
    last_seen_at: datetime
    is_stale: bool
    stale_after_seconds: int
    rate_record_id: int
    raw_record_id: int
    source_url: str
    calculation_basis: Literal[
        "stored_reference_rate_estimate",
        "stored_sampled_transfer_rate_estimate",
        "stored_treasury_side_estimate",
        "stored_treasury_rate_estimate",
    ] = "stored_reference_rate_estimate"
    transfer_route_verified: Literal[False] = False
    executable: Literal[False] = False
    metadata: dict = Field(default_factory=dict)
    warnings: list[str]


class FxQuoteRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {"source_currency": "USD", "target_currency": "NGN", "source_amount": "100.00"},
                {"source_currency": "USD", "target_currency": "NGN", "target_amount": "100000.00"},
            ]
        },
    )

    source_currency: Currency = Field(examples=["USD"])
    target_currency: Currency = Field(examples=["NGN"])
    source_amount: Amount | None = Field(
        default=None, description="Supply this or target_amount, never both."
    )
    target_amount: Amount | None = Field(
        default=None, description="Supply this or source_amount, never both."
    )

    @model_validator(mode="after")
    def validate_scenario(self):
        if (self.source_amount is None) == (self.target_amount is None):
            raise PydanticCustomError(
                "fx_amount_basis", "Supply exactly one of source_amount or target_amount"
            )
        if self.source_currency == self.target_currency:
            raise PydanticCustomError(
                "fx_currency_pair", "Source and target currencies must differ"
            )
        return self

    @property
    def amount_basis(self) -> str:
        return "source" if self.source_amount is not None else "target"

    @property
    def requested_amount(self) -> Decimal:
        return self.source_amount if self.source_amount is not None else self.target_amount


class FxReferenceRate(BaseModel):
    source_currency: Currency
    target_currency: Currency
    rate: Positive
    provider_time: datetime

    @model_validator(mode="after")
    def require_timezone(self):
        if self.provider_time.tzinfo is None:
            raise ValueError("Provider rate timestamp must include a timezone")
        return self


class FxReferenceRateRead(FxReferenceRate):
    provider: str
    id: int
    classification: Literal["reference_rate"] = "reference_rate"
    transfer_route_verified: Literal[False] = False
    captured_at: datetime
    last_seen_at: datetime
    source_url: str
    raw_record_id: int


class FxFeeRead(BaseModel):
    kind: str
    amount: Decimal | None = None
    currency: Currency | None = None
    label: str | None = None
    source_field: str
    is_total: bool = False
    relationship: Literal["included_in_source_amount", "unknown"] = "unknown"


class FxPaymentOptionRead(BaseModel):
    option_index: int
    pay_in: str | None = None
    pay_out: str | None = None
    pay_in_product: str | None = None
    disabled: bool | None = None
    disabled_reason: dict | None = None
    source_currency: Currency | None = None
    target_currency: Currency | None = None
    source_amount: Nonnegative | None = None
    target_amount: Nonnegative | None = None
    fee_total: Nonnegative | None = None
    fee_currency: Currency | None = None
    fees: list[FxFeeRead] = Field(default_factory=list)
    provider_fee_summary: dict | None = None
    provider_price: dict | None = None
    total_source_amount: Nonnegative | None = None
    net_target_amount: Nonnegative | None = None
    effective_rate: Nonnegative | None = None
    fee_treatment: Literal["included_in_source_amount", "unknown"] = "unknown"
    cost_information: Literal["complete", "partial", "unknown"] = "unknown"
    cost_scope: Literal["provider_quoted_costs_only"] = "provider_quoted_costs_only"
    external_charges_included: Literal[False] = False
    estimated_delivery: datetime | None = None
    formatted_estimated_delivery: str | None = None
    estimated_delivery_delays: list[dict] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class FxQuoteRead(BaseModel):
    provider: str
    observation_scope: Literal["amount_specific_historical_observation"] = (
        "amount_specific_historical_observation"
    )
    usable_as_fee_rule: Literal[False] = False
    id: int | None = None
    classification: Literal["illustrative_transfer_quote"] = "illustrative_transfer_quote"
    executable: Literal[False] = False
    rate_locked: Literal[False] = False
    source_currency: Currency
    target_currency: Currency
    requested_amount: Amount
    amount_basis: Literal["source", "target"]
    provider_rate: Positive | None = None
    source_amount: Nonnegative | None = None
    target_amount: Nonnegative | None = None
    provider_quote_id: str | None = None
    provider_created_at: datetime | None = None
    provider_rate_time: datetime | None = None
    expires_at: datetime | None = None
    rate_expires_at: datetime | None = None
    captured_at: datetime
    source_url: str
    api_version: str
    raw_record_id: int | None = None
    fetch_run_id: int | None = None
    payment_options: list[FxPaymentOptionRead] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class FxCurrencyRecord(BaseModel):
    code: Currency
    name: str | None = Field(default=None, min_length=1)
    symbol: str | None = None
    supports_decimals: StrictBool | None = None
    country_keywords: list[str] = Field(default_factory=list)


class FxCurrencyRead(FxCurrencyRecord):
    discovery_basis: Literal["provider_catalogue", "observed_rate_pairs"] = "provider_catalogue"
    id: int | None
    provider: str
    decimal_places: int | None
    precision_source: str | None
    captured_at: datetime
    source_url: str
    raw_record_id: int
    transfer_route_verified: Literal[False] = False


class FxTransferRateRead(BaseModel):
    """Amount-specific transfer-rate sample, distinct from a market reference rate."""

    id: int | None = None
    provider: str
    classification: Literal["transfer_rate_observation"] = "transfer_rate_observation"
    source_currency: Currency
    target_currency: Currency
    requested_destination_amount: Positive
    rate: Positive
    rate_direction: Literal["target_per_source"] = "target_per_source"
    returned_source_amount: Positive
    returned_destination_amount: Positive
    provider_time: datetime | None = None
    expires_at: datetime | None = None
    captured_at: datetime
    source_url: str
    api_version: str
    raw_record_id: int | None = None
    fetch_run_id: int | None = None
    transfer_route_verified: Literal[False] = False


class FxTreasuryRateRead(BaseModel):
    id: int
    provider: str
    classification: Literal["treasury_rate"] = "treasury_rate"
    source_currency: Currency = Field(
        description="Provider baseCurrency; customer source mapping is unverified."
    )
    target_currency: Currency = Field(
        description="Provider quoteCurrency; customer target mapping is unverified."
    )
    rate: Positive = Field(description="Original provider price; customer mapping is unverified.")
    side: Literal["buy", "sell"]
    side_perspective: Literal["unverified"] = "unverified"
    rate_direction: Literal["unverified"] = "unverified"
    provider_time: None = None
    feed_timestamp: datetime | None = None
    captured_at: datetime
    last_seen_at: datetime
    source_url: str
    raw_record_id: int
    transfer_route_verified: Literal[False] = False


FxStoredRateRead = Annotated[
    FxReferenceRateRead | FxTransferRateRead | FxTreasuryRateRead,
    Field(discriminator="classification"),
]
