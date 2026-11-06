"""Local-only arithmetic over stored reference rates and sampled transfer rates."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal, localcontext
from typing import Literal

from app.core import config
from app.core.exceptions import AppError
from app.models.enums import MarketCategory
from app.repositories.fincra import FincraRepository
from app.repositories.fx import FxRepository
from app.repositories.provider import ProviderRepository
from app.schemas.common import ApiResponse, build_paginated_response
from app.schemas.fx import (
    FxConversionRead,
    FxCurrencyRead,
    FxReferenceRateRead,
    FxTransferRateRead,
)
from app.utils.currency_precision import currency_precision


def utc(value):
    # PostgreSQL returns aware datetimes; SQLite strips tzinfo in isolated tests.
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


@dataclass(frozen=True)
class StoredConversionRate:
    """A customer direction over stored data, with any mapping assumption disclosed."""

    provider: str
    source_currency: str
    target_currency: str
    rate: Decimal
    classification: Literal["reference_rate", "transfer_rate_observation", "treasury_rate"]
    observed_at: datetime
    captured_at: datetime
    provider_rate_timestamp: datetime | None
    expires_at: datetime | None
    rate_record_id: int
    raw_record_id: int
    fetch_run_id: int
    source_url: str
    sample: FxTransferRateRead | None = None
    metadata: dict = field(default_factory=dict)


class FxService:
    def __init__(self, db, *, stale_after_seconds=None, now=None):
        self.repository = FxRepository(db)
        self.treasury = FincraRepository(db)
        self.providers = ProviderRepository(db)
        self.stale_after_seconds = (
            config.FX_RATE_STALE_AFTER_SECONDS
            if stale_after_seconds is None
            else stale_after_seconds
        )
        self.now = now or (lambda: datetime.now(UTC))

    def _get_provider(self, slug):
        provider = self.providers.get_by_slug(slug)
        if provider is None or provider.category != MarketCategory.FX or not provider.is_active:
            raise AppError(
                "FX provider is unavailable", status_code=404, error_code="fx_provider_unavailable"
            )
        return provider

    def list_rates(self, provider, *, source=None, target=None, page=1, per_page=20):
        registered = self._get_provider(provider)
        if provider == "fincra":
            items, total = self.treasury.list_rates(
                source=source,
                target=target,
                page=page,
                per_page=per_page,
            )
            return build_paginated_response(
                items=items,
                page=page,
                per_page=per_page,
                total=total,
                message="Stored treasury prices; provider buy/sell perspective is unverified",
            )
        if (registered.metadata_json or {}).get(
            "rate_classification"
        ) == "transfer_rate_observation":
            rows, total = self.repository.list_transfer_rates(
                provider_id=registered.id,
                source=source,
                target=target,
                page=page,
                per_page=per_page,
            )
            return build_paginated_response(
                items=[self.repository.transfer_rate_read(row) for row in rows],
                page=page,
                per_page=per_page,
                total=total,
                message="Stored sampled transfer rates; sampled amounts are not guaranteed prices",
            )
        rows, total = self.repository.list_rates(
            provider=provider,
            source=source,
            target=target,
            page=page,
            per_page=per_page,
        )
        return build_paginated_response(
            items=[
                FxReferenceRateRead(
                    provider=row.provider.value,
                    id=row.id,
                    source_currency=row.base_currency,
                    target_currency=row.quote_currency,
                    rate=row.metadata_json["provider_rate"],
                    provider_time=row.metadata_json["provider_time"],
                    captured_at=row.captured_at,
                    last_seen_at=row.last_seen_at,
                    source_url=row.metadata_json["source_url"],
                    raw_record_id=row.raw_record_id,
                )
                for row in rows
            ],
            page=page,
            per_page=per_page,
            total=total,
            message="Stored FX reference rates; transfer-route availability is not established",
        )

    def list_currencies(self, provider, *, page=1, per_page=20):
        registered = self._get_provider(provider)
        if provider == "fincra":
            items, total = self.treasury.currencies(page=page, per_page=per_page)
            return build_paginated_response(
                items=items,
                page=page,
                per_page=per_page,
                total=total,
                message=(
                    "Currencies observed in stored Fincra rates; not an official transfer catalogue"
                ),
            )
        rows, total = self.repository.list_currencies(
            provider_id=registered.id,
            page=page,
            per_page=per_page,
        )
        return build_paginated_response(
            items=[
                FxCurrencyRead(
                    provider=provider,
                    id=row.id,
                    code=row.code,
                    name=row.name,
                    symbol=row.symbol,
                    supports_decimals=row.supports_decimals,
                    country_keywords=row.country_keywords or [],
                    decimal_places=row.decimal_places,
                    precision_source=row.precision_source,
                    captured_at=row.captured_at,
                    source_url=row.source_url,
                    raw_record_id=row.raw_record_id,
                )
                for row in rows
            ],
            page=page,
            per_page=per_page,
            total=total,
            message="Stored FX currencies; this is not a supported-route matrix"
            if total
            else "Automatic currency discovery is not implemented for this provider"
            if (registered.metadata_json or {}).get("currency_discovery") == "not_implemented"
            else "No stored currencies for this FX provider; run currency ingestion",
        )

    def _resolve_fincra_rate(self, request):
        """Temporary user-authorized policy, pending Fincra confirmation.

        Assume Fincra buys/sells the BASE currency, priced in QUOTE per BASE.
        Giving base uses its BUY price. Giving quote uses the reciprocal SELL
        price. Prefer a direct BUY record, otherwise a reversed-pair SELL.
        Keep this rule here so provider confirmation requires one mapping change.
        """
        row = self.treasury.get_rate(request.source_currency, request.target_currency, "buy")
        inverted = row is None
        if inverted:
            row = self.treasury.get_rate(request.target_currency, request.source_currency, "sell")
        if row is None:
            raise AppError(
                "No stored Fincra price exists for this customer direction",
                status_code=503,
                error_code="fx_rate_unavailable",
            )
        try:
            original = self.treasury.read(row)
            if (
                original.side != ("sell" if inverted else "buy")
                or not original.source_url
                or row.raw_record_id is None
            ):
                raise ValueError("Invalid stored treasury provenance")
            with localcontext() as context:
                # Recurring reciprocals need an explicit precision independent
                # of the caller's decimal context. Gross calculation stays Decimal.
                context.prec = max(
                    64,
                    len(original.rate.as_tuple().digits)
                    + len(request.source_amount.as_tuple().digits)
                    + 16,
                )
                context.rounding = ROUND_HALF_UP
                rate = Decimal(1) / original.rate if inverted else original.rate
            return StoredConversionRate(
                provider="fincra",
                source_currency=request.source_currency,
                target_currency=request.target_currency,
                rate=rate,
                classification="treasury_rate",
                observed_at=utc(row.last_seen_at),
                captured_at=utc(row.captured_at),
                provider_rate_timestamp=None,
                expires_at=None,
                rate_record_id=row.id,
                raw_record_id=row.raw_record_id,
                fetch_run_id=row.fetch_run_id,
                source_url=original.source_url,
                metadata={
                    "fincra_mapping": {
                        "status": "assumed",
                        "policy": "provider_base_currency_v1",
                        "side_perspective": "provider",
                        "price_units": "quote_per_base",
                        "selection_policy": "direct_buy_then_reverse_sell",
                        "provider_side": original.side,
                        "base_currency": row.base_currency,
                        "quote_currency": row.quote_currency,
                        "provider_price": str(original.rate),
                        "inverted": inverted,
                    }
                },
            )
        except (KeyError, TypeError, ValueError, ArithmeticError):
            raise AppError(
                "Stored Fincra price or provenance is invalid",
                status_code=503,
                error_code="fx_rate_unavailable",
            ) from None

    def _resolve_conversion_rate(self, request, provider):
        """Resolve stored customer directions without provider requests or cross-rates."""
        provider_key = provider.slug
        if provider_key == "fincra":
            return self._resolve_fincra_rate(request)
        row = self.repository.get_rate(
            provider=provider_key,
            source=request.source_currency,
            target=request.target_currency,
        )
        sample = None
        try:
            if row is None:
                row = self.repository.get_transfer_rate(
                    provider_id=provider.id,
                    source=request.source_currency,
                    target=request.target_currency,
                )
                if row is None:
                    raise AppError(
                        "No direct stored rate exists for this provider and direction",
                        status_code=503,
                        error_code="fx_rate_unavailable",
                    )
                sample = self.repository.transfer_rate_read(row)
                rate, timestamp = sample.rate, sample.provider_time
                expires_at, source_url = sample.expires_at, sample.source_url
                observed_at = utc(row.captured_at)
                if (
                    sample.provider != provider_key
                    or sample.source_currency != request.source_currency
                    or sample.target_currency != request.target_currency
                ):
                    raise ValueError("Stored sample does not match the requested direction")
            else:
                metadata = row.metadata_json or {}
                rate = Decimal(metadata["provider_rate"])
                timestamp = datetime.fromisoformat(metadata["provider_time"])
                if timestamp.tzinfo is None:
                    raise ValueError("Provider timestamp must have a time zone")
                observed_at = utc(row.last_seen_at)
                source_url, expires_at = metadata["source_url"], None
            if not rate.is_finite() or rate <= 0 or not source_url or row.raw_record_id is None:
                raise ValueError("Invalid stored rate or provenance")
            return StoredConversionRate(
                provider=provider_key,
                source_currency=request.source_currency,
                target_currency=request.target_currency,
                rate=rate,
                classification="transfer_rate_observation" if sample else "reference_rate",
                observed_at=observed_at,
                captured_at=utc(row.captured_at),
                provider_rate_timestamp=utc(timestamp) if timestamp is not None else None,
                expires_at=utc(expires_at) if expires_at is not None else None,
                rate_record_id=row.id,
                raw_record_id=row.raw_record_id,
                fetch_run_id=row.fetch_run_id,
                source_url=source_url,
                sample=sample,
            )
        except (KeyError, TypeError, ValueError, ArithmeticError):
            raise AppError(
                "Stored rate has invalid precision, timestamp or provenance metadata",
                status_code=503,
                error_code="fx_rate_unavailable",
            ) from None

    def convert(self, request):
        if self.stale_after_seconds <= 0:
            raise AppError(
                "FX calculation configuration is invalid",
                status_code=503,
                error_code="fx_not_configured",
            )
        provider = self._get_provider(request.provider.value)
        stored = self._resolve_conversion_rate(request, provider)
        rate, timestamp, sample = stored.rate, stored.provider_rate_timestamp, stored.sample
        currency = self.repository.get_currency(
            provider_id=provider.id,
            code=request.target_currency,
        )
        if currency:
            places, precision_source = currency.decimal_places, currency.precision_source
        else:
            places, precision_source = currency_precision(request.target_currency)
        # No existing fee profile establishes verified scenario applicability and
        # source/target fee treatment for these rates. A diagnostic quote, even
        # one with a zero fee, is not a reusable conversion fee rule.
        warnings = [
            "Estimate from stored reference rates; transfer-route availability is not verified.",
            "Fees are unavailable and excluded. The gross amount is not a provider delivery quote.",
        ]
        metadata = {"fetch_run_id": stored.fetch_run_id, **stored.metadata}
        if stored.classification == "treasury_rate":
            warnings = [
                "Estimate using an assumed Fincra mapping: Fincra buys/sells the base currency "
                "and prices are quote units per base unit. Provider confirmation is pending.",
                "Fees are unavailable and excluded; "
                "any spread in the stored price is not added again.",
                "No provider valuation time was supplied; "
                "freshness uses the last observation time.",
            ]
        if sample:
            warnings = [
                "Estimate from a stored transfer rate sampled for destination amount "
                f"{sample.requested_destination_amount} {sample.target_currency}.",
                "The sampled price is not guaranteed for this amount or any payout method.",
                "Separate fees are unavailable; this is not the final debit or recipient payout.",
            ]
            metadata["pricing_scope"] = {
                "amount_basis": "target",
                "requested_target_amount": str(sample.requested_destination_amount),
                "returned_source_amount": str(sample.returned_source_amount),
                "returned_target_amount": str(sample.returned_destination_amount),
                "extrapolated": request.source_amount != sample.returned_source_amount,
                "selection_policy": (
                    "latest_collection_then_smallest_destination_amount_then_newest_id"
                ),
            }
            if metadata["pricing_scope"]["extrapolated"]:
                warnings.append("Calculation extrapolates beyond the original sampled amount.")
            if timestamp is None:
                warnings.append(
                    "No provider timestamp was supplied; freshness uses collection time."
                )
        with localcontext() as context:
            context.prec = max(
                36, len(rate.as_tuple().digits) + len(request.source_amount.as_tuple().digits) + 8
            )
            gross = request.source_amount * rate
            displayed = (
                gross.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)
                if places is not None
                else gross
            )
        now = utc(self.now())
        freshness_time = timestamp if timestamp is not None else stored.observed_at
        is_stale = (now - freshness_time).total_seconds() > self.stale_after_seconds
        if stored.expires_at is not None and now >= stored.expires_at:
            is_stale = True
            warnings.append("The stored rate has expired; this is a historical estimate.")
        if is_stale:
            warnings.append("The provider rate is stale; no automatic refresh was attempted.")
        if places is None:
            warnings.append("Target currency precision is unknown; the gross amount is unrounded.")
        result = FxConversionRead(
            provider=stored.provider,
            source_currency=stored.source_currency,
            target_currency=stored.target_currency,
            source_amount=request.source_amount,
            reference_rate=rate if stored.classification == "reference_rate" else None,
            applied_rate=rate,
            rate_classification=stored.classification,
            sampled_destination_amount=sample.requested_destination_amount if sample else None,
            sample_source_amount=sample.returned_source_amount if sample else None,
            sample_target_amount=sample.returned_destination_amount if sample else None,
            sample_selection_policy=metadata["pricing_scope"]["selection_policy"]
            if sample
            else None,
            freshness_basis="provider_timestamp"
            if timestamp is not None
            else "collection_timestamp",
            calculation_basis="stored_treasury_rate_estimate"
            if stored.classification == "treasury_rate"
            else "stored_sampled_transfer_rate_estimate"
            if sample
            else "stored_reference_rate_estimate",
            gross_target_amount=displayed,
            unrounded_gross_target_amount=gross,
            target_decimal_places=places,
            precision_source=precision_source,
            rounding_policy="ROUND_HALF_UP" if places is not None else "unrounded",
            fee_status="unavailable",
            fee_amount=None,
            fee_currency=None,
            net_target_amount=None,
            estimated_net_target_amount=None,
            observed_at=stored.observed_at,
            provider_rate_timestamp=timestamp,
            expires_at=stored.expires_at,
            captured_at=stored.captured_at,
            last_seen_at=stored.observed_at,
            is_stale=is_stale,
            stale_after_seconds=self.stale_after_seconds,
            rate_record_id=stored.rate_record_id,
            raw_record_id=stored.raw_record_id,
            source_url=stored.source_url,
            metadata=metadata,
            warnings=warnings,
        )
        return ApiResponse(
            responseCode=200, message="Local estimate before fees from stored rates", data=result
        )
