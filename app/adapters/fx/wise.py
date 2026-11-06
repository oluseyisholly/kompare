"""Wise data only: reference rates and non-executable illustrative transfer quotes."""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation, localcontext
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse

import httpx
from pydantic import AwareDatetime, TypeAdapter

from app.core import config
from app.core.exceptions import AppError
from app.schemas.fx import (
    FxCurrencyRecord,
    FxFeeRead,
    FxPaymentOptionRead,
    FxQuoteRead,
    FxQuoteRequest,
    FxReferenceRate,
)


@dataclass
class WiseResponse:
    source_url: str
    status_code: int
    payload: object
    raw_text: str
    retry_after: float | None = None
    pagination_pending: bool = False


def wise_error(message, code="wise_provider_failure", status=502, **data):
    return AppError(message, status_code=status, error_code=code, data=data)


def json_safe(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    return value


def optional_number(value, *, nonnegative=True):
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("Invalid numeric value")
    try:
        number = Decimal(str(value))
    except InvalidOperation:
        raise ValueError("Invalid numeric value") from None
    if not number.is_finite() or (nonnegative and number < 0):
        raise ValueError("Invalid numeric value")
    return number


def optional_time(value):
    return TypeAdapter(AwareDatetime).validate_python(value) if value is not None else None


class WiseAdapter:
    def __init__(self, *, token=None, quote_token=None, base_url=None, api_version=None):
        self.token = (config.WISE_API_TOKEN if token is None else token).strip()
        self.quote_token = (
            config.WISE_QUOTE_CLIENT_TOKEN if quote_token is None else quote_token
        ).strip()
        self.base_url = (base_url or config.WISE_BASE_URL).rstrip("/")
        self.api_version = api_version or config.WISE_API_VERSION

    def endpoint(self, resource):
        # Check only when Wise is used, not during application startup.
        parsed = urlparse(self.base_url)
        if (
            parsed.scheme != "https"
            or parsed.netloc not in {"api.wise.com", "api.wise-sandbox.com"}
            or parsed.path
            or parsed.query
            or parsed.fragment
            or not re.fullmatch(r"\d{4}Q[1-4]", self.api_version)
        ):
            raise wise_error("Wise endpoint configuration is invalid", "wise_not_configured", 503)
        return f"{self.base_url}/{self.api_version}/{resource}"

    @staticmethod
    def _retry_after(value):
        if not value:
            return None
        try:
            seconds = float(value)
        except ValueError:
            try:
                seconds = (parsedate_to_datetime(value) - datetime.now(UTC)).total_seconds()
            except (ValueError, TypeError, OverflowError):
                return None
        return max(0, seconds) if Decimal(str(seconds)).is_finite() else None

    async def _request(self, method, resource, *, client, body=None, token=""):
        url = self.endpoint(resource)
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        for attempt in range(2):
            try:
                response = await client.request(
                    method,
                    url,
                    headers=headers,
                    content=body,
                    timeout=15,
                    follow_redirects=False,
                )
            except httpx.TransportError as exc:
                safe_to_retry = method == "GET" or isinstance(
                    exc, (httpx.ConnectError, httpx.ConnectTimeout)
                )
                if not attempt and safe_to_retry:
                    await asyncio.sleep(0.5)
                    continue
                raise wise_error("Wise could not be reached", "wise_unavailable", 503) from None
            delay = self._retry_after(response.headers.get("Retry-After"))
            if response.status_code == 429 and not attempt and (delay is None or delay <= 2):
                await asyncio.sleep((0.5 if delay is None else delay) + 0.05)
                continue
            # Never persist credentials, including an upstream error that echoes one.
            text = response.text
            for secret in (self.token, self.quote_token):
                if secret:
                    text = text.replace(secret, "[REDACTED]")
            try:
                payload = json.loads(text, parse_float=Decimal)
            except (ValueError, TypeError):
                payload = None
            return WiseResponse(
                url,
                response.status_code,
                payload,
                text,
                delay,
                pagination_pending=bool(response.links.get("next") or response.links.get("prev")),
            )

    async def fetch_rates(self, *, client):
        if not self.token:
            raise wise_error("WISE_API_TOKEN is not configured", "wise_not_configured", 503)
        # No source/target filters: request all pairs available to these credentials.
        return await self._request("GET", "rates", client=client, token=self.token)

    async def fetch_currencies(self, *, client):
        if not self.token:
            raise wise_error("WISE_API_TOKEN is not configured", "wise_not_configured", 503)
        return await self._request("GET", "currencies", client=client, token=self.token)

    @staticmethod
    def parse_currencies(payload):
        if not isinstance(payload, list) or not payload:
            raise ValueError("Expected a nonempty Wise currency array")
        records, failures, seen, duplicates = [], [], set(), set()
        for index, item in enumerate(payload):
            try:
                if not isinstance(item.get("supportsDecimals"), bool) or not item.get("name"):
                    raise ValueError("Missing Wise currency name or decimal-support flag")
                record = FxCurrencyRecord(
                    code=item["code"],
                    name=item["name"],
                    symbol=item.get("symbol"),
                    supports_decimals=item["supportsDecimals"],
                    country_keywords=item.get("countryKeywords", []),
                )
                if record.code in seen:
                    duplicates.add(record.code)
                    raise ValueError("Duplicate currency code")
                seen.add(record.code)
                records.append(record)
            except (ValueError, KeyError, TypeError, AttributeError):
                failures.append({"index": index, "error": "Invalid or duplicate Wise currency"})
        return [r for r in records if r.code not in duplicates], failures

    async def fetch_quote(self, request: FxQuoteRequest, *, client):
        fields = {
            "sourceCurrency": request.source_currency,
            "targetCurrency": request.target_currency,
            "sourceAmount"
            if request.amount_basis == "source"
            else "targetAmount": request.requested_amount,
        }
        # Encode validated Decimal amounts as JSON numbers, without a float round-trip.
        body = (
            "{"
            + ",".join(
                json.dumps(key)
                + ":"
                + (format(value, "f") if isinstance(value, Decimal) else json.dumps(value))
                for key, value in fields.items()
            )
            + "}"
        )
        return await self._request(
            "POST", "quotes", client=client, body=body, token=self.quote_token
        )

    @staticmethod
    def check_response(response):
        payload = response.payload
        errors = payload.get("errors", []) if isinstance(payload, dict) else []
        if not isinstance(errors, list):
            errors = []
        codes = [error.get("code") for error in errors if isinstance(error, dict)]
        codes = [c for c in codes if isinstance(c, str) and re.fullmatch(r"[\w.-]{1,120}", c)]
        if response.status_code < 300 and response.status_code >= 200 and not errors:
            if payload is None:
                raise wise_error("Wise returned invalid JSON", "wise_invalid_response")
            return
        data = {"provider_status": response.status_code, "provider_error_codes": codes}
        if "error.route.not.supported" in codes:
            raise wise_error(
                "Wise does not support this transfer scenario",
                "wise_unsupported_route",
                422,
                **data,
            )
        if response.status_code in {401, 403} or "error.quote.mustBeAuthenticated" in codes:
            raise wise_error(
                "Wise access is unavailable; verify environment, permissions or partner access",
                "wise_access_unavailable",
                503,
                **data,
            )
        if response.status_code == 429:
            raise wise_error(
                "Wise rate limit reached",
                "wise_rate_limited",
                503,
                retry_after=response.retry_after,
                **data,
            )
        if response.status_code in {400, 422}:
            raise wise_error(
                "Wise rejected this quote scenario", "wise_invalid_scenario", 422, **data
            )
        raise wise_error("Wise data is currently unavailable", **data)

    @staticmethod
    def parse_rates(payload):
        if not isinstance(payload, list) or not payload:
            raise ValueError("Expected a nonempty Wise rates array")
        records, failures, seen, duplicates = [], [], set(), set()
        for index, item in enumerate(payload):
            try:
                record = FxReferenceRate(
                    source_currency=item["source"],
                    target_currency=item["target"],
                    rate=item["rate"],
                    provider_time=item["time"],
                )
                key = (record.source_currency, record.target_currency)
                if key in seen:
                    duplicates.add(key)
                    raise ValueError("Duplicate reference-rate pair")
                seen.add(key)
                records.append(record)
            except (ValueError, KeyError, TypeError):
                failures.append(
                    {"index": index, "error": "Invalid or duplicate Wise reference rate"}
                )
        return [
            r for r in records if (r.source_currency, r.target_currency) not in duplicates
        ], failures

    def parse_quote(self, payload, *, request, captured_at, source_url):
        if not isinstance(payload, dict):
            raise ValueError("Expected a Wise quote object")
        if (payload.get("sourceCurrency"), payload.get("targetCurrency")) != (
            request.source_currency,
            request.target_currency,
        ):
            raise ValueError("Wise quote currencies do not match the requested scenario")
        if (
            payload.get("providedAmountType", request.amount_basis.upper())
            != request.amount_basis.upper()
        ):
            raise ValueError("Wise quote amount basis does not match the request")
        requested_field = "sourceAmount" if request.amount_basis == "source" else "targetAmount"
        if (
            payload.get(requested_field) is not None
            and optional_number(payload[requested_field]) != request.requested_amount
        ):
            raise ValueError("Wise changed the requested amount")
        options = payload.get("paymentOptions", [])
        if not isinstance(options, list):
            raise ValueError("Wise paymentOptions must be an array")
        parsed = []
        for index, option in enumerate(options):
            try:
                parsed.append(self._parse_option(option, index=index, request=request))
            except (ValueError, TypeError, KeyError, AttributeError):
                # Do not hide malformed or disabled payment options by choosing another.
                methods = {
                    key: option.get(provider_key)
                    for key, provider_key in (("pay_in", "payIn"), ("pay_out", "payOut"))
                    if isinstance(option, dict) and isinstance(option.get(provider_key), str)
                }
                parsed.append(
                    FxPaymentOptionRead(
                        option_index=index,
                        **methods,
                        warnings=[
                            "Payment option could not be parsed; inspect retained raw evidence"
                        ],
                    )
                )
        return FxQuoteRead(
            provider="wise",
            source_currency=request.source_currency,
            target_currency=request.target_currency,
            requested_amount=request.requested_amount,
            amount_basis=request.amount_basis,
            provider_rate=optional_number(payload.get("rate")),
            source_amount=optional_number(payload.get("sourceAmount")),
            target_amount=optional_number(payload.get("targetAmount")),
            provider_quote_id=payload.get("id"),
            provider_created_at=optional_time(payload.get("createdTime")),
            provider_rate_time=optional_time(payload.get("rateTimestamp")),
            expires_at=optional_time(payload.get("expirationTime")),
            rate_expires_at=optional_time(payload.get("rateExpirationTime")),
            captured_at=captured_at,
            source_url=source_url,
            api_version=self.api_version,
            payment_options=parsed,
            warnings=[] if parsed else ["Wise returned no payment options or fee information"],
        )

    @staticmethod
    def _parse_option(option, *, index, request):
        if not isinstance(option, dict):
            raise ValueError("Expected a payment option")
        source = option.get("sourceCurrency", request.source_currency)
        target = option.get("targetCurrency", request.target_currency)
        source_amount = optional_number(option.get("sourceAmount"))
        target_amount = optional_number(option.get("targetAmount"))
        price = option.get("price") or {}
        summary = option.get("fee") or {}
        total = (price.get("total") or {}).get("value") or {}
        price_total = optional_number(total.get("amount"))
        summary_total = optional_number(summary.get("total"))
        fee_total = price_total if price_total is not None else summary_total
        fee_currency = total.get("currency")
        warnings, fees = [], []
        fee_conflict = (
            price_total is not None and summary_total is not None and price_total != summary_total
        )
        if fee_conflict:
            warnings.append("Wise fee summary and price total disagree")
        if fee_total is not None:
            fees.append(
                FxFeeRead(
                    kind="total",
                    amount=fee_total,
                    currency=fee_currency,
                    is_total=True,
                    source_field="price.total" if price_total is not None else "fee.total",
                )
            )
        for item in price.get("items", []):
            value = item.get("value") or {}
            fees.append(
                FxFeeRead(
                    kind=item.get("type", "unknown"),
                    amount=optional_number(value.get("amount"), nonnegative=False),
                    currency=value.get("currency"),
                    label=item.get("label"),
                    source_field="price.items",
                )
            )
        if not price.get("items"):
            for kind in ("transferwise", "payIn", "discount", "partner"):
                if kind in summary:
                    fees.append(
                        FxFeeRead(
                            kind=kind,
                            amount=optional_number(summary[kind]),
                            currency=fee_currency,
                            source_field=f"fee.{kind}",
                        )
                    )
        requested_value = source_amount if request.amount_basis == "source" else target_amount
        matches = source == request.source_currency and target == request.target_currency
        if requested_value is not None and requested_value != request.requested_amount:
            warnings.append("Payment option changes the requested amount")
            matches = False
        if not matches:
            warnings.append("Payment option does not match the requested scenario")
        amounts_known = (
            matches
            and source_amount is not None
            and source_amount > 0
            and target_amount is not None
        )
        fee_known = fee_total is not None and fee_currency == source and not fee_conflict
        deferred = price.get("deferredFee")
        if deferred and optional_number(deferred.get("amount")) != 0:
            warnings.append("Additional deferred fees are not included in this calculation")
            fee_known = False
        if not fee_known:
            warnings.append("Fee information is incomplete; no effective rate calculated")
        complete = amounts_known and fee_known
        treatment = "included_in_source_amount" if complete else "unknown"
        for fee in fees:
            if complete and fee.currency == source:
                fee.relationship = treatment
        effective_rate = None
        if complete and option.get("disabled") is False:
            with localcontext() as context:
                context.prec = 36
                effective_rate = target_amount / source_amount
        return FxPaymentOptionRead(
            option_index=index,
            pay_in=option.get("payIn"),
            pay_out=option.get("payOut"),
            pay_in_product=option.get("payInProduct"),
            disabled=option.get("disabled"),
            disabled_reason=json_safe(option.get("disabledReason")),
            source_currency=source,
            target_currency=target,
            source_amount=source_amount,
            target_amount=target_amount,
            fee_total=None if fee_conflict else fee_total,
            fee_currency=fee_currency,
            fees=fees,
            provider_fee_summary=json_safe(option.get("fee")),
            provider_price=json_safe(option.get("price")),
            total_source_amount=source_amount if amounts_known else None,
            net_target_amount=target_amount if amounts_known else None,
            effective_rate=effective_rate,
            fee_treatment=treatment,
            cost_information="complete"
            if complete
            else "partial"
            if any(value is not None for value in (source_amount, target_amount, fee_total))
            else "unknown",
            estimated_delivery=optional_time(option.get("estimatedDelivery")),
            formatted_estimated_delivery=option.get("formattedEstimatedDelivery"),
            estimated_delivery_delays=option.get("estimatedDeliveryDelays") or [],
            warnings=warnings,
        )
