"""Flutterwave v3 transfer-rate sampling; no transfer or payment operations."""

import asyncio
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from email.utils import parsedate_to_datetime
from typing import Annotated

import httpx
from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic_core import PydanticCustomError

from app.core import config
from app.core.exceptions import AppError
from app.schemas.fx import Currency, FxTransferRateRead

RATES_URL = "https://api.flutterwave.com/v3/transfers/rates"
# Collection targets, not a claim of account-specific route availability. The
# provider still validates every request; unsupported pairs fail independently.
DEFAULT_SCENARIOS = [
    {"source_currency": "NGN", "destination_currency": "USD", "destination_amount": "1000"},
    {"source_currency": "USD", "destination_currency": "NGN", "destination_amount": "100000"},
    {"source_currency": "NGN", "destination_currency": "GBP", "destination_amount": "1000"},
    {"source_currency": "GBP", "destination_currency": "NGN", "destination_amount": "100000"},
    {"source_currency": "NGN", "destination_currency": "EUR", "destination_amount": "1000"},
    {"source_currency": "EUR", "destination_currency": "NGN", "destination_amount": "100000"},
]


class FlutterwaveScenario(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_currency: Currency
    destination_currency: Currency
    # The v3 reference declares amount as int32. Keep the first version within
    # that documented domain; do not assume fractional request amounts work.
    destination_amount: Annotated[
        Decimal, Field(gt=0, le=2147483647, decimal_places=0, allow_inf_nan=False)
    ]

    @model_validator(mode="after")
    def different_currencies(self):
        if self.source_currency == self.destination_currency:
            raise PydanticCustomError("flutterwave_pair", "Source and destination must differ")
        return self


@dataclass
class FlutterwaveResponse:
    status_code: int
    payload: object
    raw_text: str
    source_url: str = RATES_URL
    retry_after: float | None = None


def provider_error(message, code="flutterwave_unavailable", status=503, **data):
    return AppError(message, status_code=status, error_code=code, data=data)


def json_safe(value):
    return json.loads(json.dumps(value, default=str))


class FlutterwaveAdapter:
    def __init__(self, *, secret_key=None, mode=None, scenarios=None, base_url=None):
        self.secret_key = (
            config.FLUTTERWAVE_SECRET_KEY if secret_key is None else secret_key
        ).strip()
        # v3 uses one host: the credential prefix determines test/live access.
        self.mode = (
            mode
            if mode is not None
            else ("test" if self.secret_key.startswith("FLWSECK_TEST-") else "live")
        )
        self.base_url = (config.FLUTTERWAVE_BASE_URL if base_url is None else base_url).rstrip("/")
        self.scenario_configuration = (
            config.FLUTTERWAVE_FX_SCENARIOS if scenarios is None else scenarios
        )

    def configuration_status(self):
        if not self.secret_key:
            return "missing_credentials"
        if self.mode not in {"test", "live"}:
            return "invalid_environment"
        # Both v3 key modes use this host. Never send a secret to another origin.
        if self.base_url != "https://api.flutterwave.com":
            return "invalid_base_url"
        test_key = self.secret_key.startswith("FLWSECK_TEST-")
        live_key = self.secret_key.startswith("FLWSECK-")
        if (self.mode == "test" and not test_key) or (self.mode == "live" and not live_key):
            return "credential_environment_mismatch"
        return "configured"

    def scenarios(self):
        value = self.scenario_configuration
        if value is None or (isinstance(value, str) and not value.strip()):
            value = DEFAULT_SCENARIOS
        if isinstance(value, str):
            try:
                value = json.loads(value, parse_float=Decimal)
            except ValueError:
                return [], [{"error": "FLUTTERWAVE_FX_SCENARIOS must contain a JSON array"}]
        if not isinstance(value, list):
            return [], [{"error": "FLUTTERWAVE_FX_SCENARIOS must contain a JSON array"}]
        if not value:
            value = DEFAULT_SCENARIOS
        records, failures, seen = [], [], set()
        for index, item in enumerate(value):
            try:
                record = FlutterwaveScenario.model_validate(item)
                key = (
                    record.source_currency,
                    record.destination_currency,
                    record.destination_amount,
                )
                if key in seen:
                    raise ValueError("Duplicate scenario")
                seen.add(key)
                records.append(record)
            except (ValueError, TypeError):
                # Do not echo unvalidated configuration, which may contain secrets.
                failures.append(
                    {"index": index, "error": "Invalid or duplicate transfer-rate scenario"}
                )
        return records, failures

    @staticmethod
    def _retry_delay(value):
        if not value:
            return None
        try:
            seconds = Decimal(value)
        except ArithmeticError:
            try:
                seconds = Decimal(
                    str((parsedate_to_datetime(value) - datetime.now(UTC)).total_seconds())
                )
            except (ValueError, TypeError, OverflowError):
                return None
        return float(max(Decimal(0), seconds)) if seconds.is_finite() else None

    async def fetch_rate(self, scenario, *, client):
        if self.configuration_status() != "configured":
            raise provider_error(
                "Flutterwave credentials or mode are not configured", "flutterwave_not_configured"
            )
        for attempt in range(2):
            try:
                response = await client.get(
                    f"{self.base_url}/v3/transfers/rates",
                    params={
                        "source_currency": scenario.source_currency,
                        "destination_currency": scenario.destination_currency,
                        "amount": str(int(scenario.destination_amount)),
                    },
                    headers={
                        "Authorization": f"Bearer {self.secret_key}",
                        "Accept": "application/json",
                    },
                    timeout=15,
                    follow_redirects=False,
                )
            except httpx.TransportError:
                if not attempt:
                    await asyncio.sleep(0.5)
                    continue
                raise provider_error("Flutterwave could not be reached") from None
            delay = self._retry_delay(response.headers.get("Retry-After"))
            if response.status_code == 429 and not attempt and (delay is None or delay <= 2):
                await asyncio.sleep((0.5 if delay is None else delay) + 0.05)
                continue
            # Preserve original JSON precision; redact even an echoed key in an error body.
            original = response.text.replace(self.secret_key, "[REDACTED]")
            try:
                payload = json.loads(original, parse_float=Decimal, parse_constant=Decimal)
            except ValueError:
                payload = None
            return FlutterwaveResponse(
                response.status_code,
                payload,
                original,
                source_url=str(response.request.url),
                retry_after=delay,
            )

    @staticmethod
    def parse_rate(response, *, scenario, captured_at):
        status = response.status_code
        payload = response.payload
        details = {"provider_status": status}
        message = payload.get("message") if isinstance(payload, dict) else None
        if isinstance(message, str) and message.strip():
            # fetch_rate already redacts credentials before constructing this payload.
            details["provider_message"] = " ".join(message.split())[:500]
        if status in {401, 403}:
            raise provider_error(
                "Flutterwave access is unavailable",
                "flutterwave_access_unavailable",
                **details,
            )
        if status == 429:
            raise provider_error(
                "Flutterwave rate limit reached",
                "flutterwave_rate_limited",
                retry_after=response.retry_after,
                **details,
            )
        if status == 400:
            # A 400 can be a provider system/account error, not an unsupported pair.
            raise provider_error(
                "Flutterwave rejected the rate request; see provider_message",
                "flutterwave_request_rejected",
                502,
                **details,
            )
        if status in {404, 422}:
            raise provider_error(
                "Flutterwave cannot price this configured scenario",
                "flutterwave_scenario_unavailable",
                422,
                **details,
            )
        if status != 200:
            raise provider_error(
                "Flutterwave rate request failed",
                "flutterwave_provider_failure",
                502,
                **details,
            )
        if not isinstance(payload, dict) or payload.get("status") != "success":
            raise provider_error(
                "Flutterwave returned no usable rate for this scenario",
                "flutterwave_rate_unavailable",
                502,
                **details,
            )
        try:
            data = payload["data"]
            record = FxTransferRateRead(
                provider="flutterwave",
                source_currency=data["source"]["currency"],
                target_currency=data["destination"]["currency"],
                requested_destination_amount=scenario.destination_amount,
                rate=data["rate"],
                returned_source_amount=data["source"]["amount"],
                returned_destination_amount=data["destination"]["amount"],
                # The documented v3 response has no provider timestamp.
                provider_time=None,
                captured_at=captured_at,
                source_url=response.source_url,
                api_version="v3",
            )
            if (
                record.source_currency != scenario.source_currency
                or record.target_currency != scenario.destination_currency
                or record.returned_destination_amount != scenario.destination_amount
            ):
                raise ValueError("Returned scenario does not match requested destination")
            return record
        except (ValueError, TypeError, KeyError):
            raise provider_error(
                "Flutterwave returned invalid transfer-rate data",
                "flutterwave_invalid_response",
                502,
            ) from None
