"""Read-only Fincra treasury-rate feed. No trading or payment endpoints."""

import asyncio
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from email.utils import parsedate_to_datetime
from typing import Annotated, Literal

import httpx
from pydantic import (
    AwareDatetime,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StrictInt,
    ValidationError,
)

from app.core import config
from app.core.exceptions import AppError
from app.schemas.fx import Currency, Positive

HOSTS = {
    "sandbox": "https://sandboxapi.fincra.com",
    "production": "https://api.fincra.com",
}
PATH = "/quotes/treasury-orders/rates"
EXCLUDED_DIGITAL_ASSETS = frozenset({"CNGN", "USDC", "USDT"})
# Provider records can contain these documented assets. Shared FX APIs remain
# restricted to currency codes; ingestion reports and excludes digital assets.
FincraCurrency = Annotated[
    Currency | Literal["CNGN", "USDC", "USDT"],
    BeforeValidator(lambda value: value.strip().upper() if isinstance(value, str) else value),
]


def failure(message, code="fincra_invalid_response", status=502, **details):
    return AppError(message, status_code=status, error_code=code, data=details)


class FincraRate(BaseModel):
    baseCurrency: FincraCurrency
    quoteCurrency: FincraCurrency
    side: Literal["buy", "sell"]
    price: Positive


class Pagination(BaseModel):
    model_config = ConfigDict(extra="ignore")
    page: StrictInt = Field(ge=1)
    perPage: StrictInt = Field(ge=1, le=1000)
    totalItems: StrictInt = Field(ge=1)
    totalPages: StrictInt = Field(ge=1, le=100)
    timestamp: AwareDatetime | None = None


@dataclass
class FincraResponse:
    status_code: int
    source_url: str
    raw_text: str
    payload: object


class FincraAdapter:
    def __init__(self, *, secret_key=None, base_url=None):
        self.secret_key = (config.FINCRA_SECRET_KEY if secret_key is None else secret_key).strip()
        configured_url = config.FINCRA_BASE_URL if base_url is None else base_url
        self.base_url = configured_url.rstrip("/")

    def configuration_status(self):
        if self.base_url not in HOSTS.values():
            return "invalid_base_url"
        return "configured" if self.secret_key else "missing_credentials"

    @staticmethod
    def retry_delay(value):
        try:
            number = Decimal(value)
            return float(max(number, Decimal(0))) if number.is_finite() else None
        except (ArithmeticError, TypeError, ValueError):
            try:
                return max(0, (parsedate_to_datetime(value) - datetime.now(UTC)).total_seconds())
            except (TypeError, ValueError, OverflowError):
                return None

    async def fetch_page(self, page, *, client):
        if self.configuration_status() != "configured":
            raise failure(
                "Fincra credentials/base URL are not configured", "fincra_not_configured", 503
            )
        url = self.base_url + PATH
        for attempt in range(2):
            try:
                response = await client.get(
                    url,
                    params={"page": page, "perPage": 10},
                    headers={"api-key": self.secret_key, "Accept": "application/json"},
                    timeout=15,
                    follow_redirects=False,
                )
            except httpx.TransportError:
                if not attempt:
                    await asyncio.sleep(0.5)
                    continue
                raise failure("Fincra could not be reached", "fincra_unavailable", 503) from None
            delay = self.retry_delay(response.headers.get("Retry-After"))
            if response.status_code == 429 and not attempt and (delay is None or delay <= 2):
                await asyncio.sleep(0.5 if delay is None else delay)
                continue
            raw = response.text.replace(self.secret_key, "[REDACTED]")
            try:
                payload = json.loads(raw, parse_float=Decimal)
            except ValueError:
                payload = None
            return FincraResponse(response.status_code, str(response.request.url), raw, payload)

    @staticmethod
    def parse_page(response, expected_page):
        if response.status_code in {401, 403}:
            raise failure(
                "Fincra access denied; verify the environment and API key",
                "fincra_access_unavailable",
                503,
            )
        if response.status_code == 429:
            raise failure("Fincra rate limit reached", "fincra_rate_limited", 503)
        if response.status_code != 200:
            raise failure("Fincra rate request failed", "fincra_provider_failure", 502)

        def invalid(reason, **details):
            return failure(f"Fincra page {expected_page}: {reason}", page=expected_page, **details)

        body = response.payload
        if not isinstance(body, dict) or body.get("success") is not True:
            raise invalid("Unsuccessful or malformed response")
        data = body.get("data")
        if not isinstance(data, dict):
            raise invalid("Missing rate data")
        try:
            paging = Pagination.model_validate(data.get("pagination"))
        except ValidationError as exc:
            raise invalid(
                "Invalid pagination",
                errors=exc.errors(include_input=False, include_context=False, include_url=False),
            ) from None
        if paging.page != expected_page or paging.page > paging.totalPages:
            raise invalid("Unexpected page", returned_page=paging.page)
        items = data.get("rates")
        if not isinstance(items, list) or not items:
            raise invalid("Empty or missing rate list")
        if paging.totalPages != (paging.totalItems + paging.perPage - 1) // paging.perPage:
            raise invalid("Inconsistent pagination")
        expected_count = min(paging.perPage, paging.totalItems - (paging.page - 1) * paging.perPage)
        if len(items) != expected_count:
            raise invalid(
                "Incomplete page", expected_count=expected_count, received_count=len(items)
            )
        records = []
        for index, item in enumerate(items, start=1):
            pair = {}
            if isinstance(item, dict):
                for field, key in (
                    ("baseCurrency", "base_currency"),
                    ("quoteCurrency", "quote_currency"),
                ):
                    code = item.get(field)
                    if isinstance(code, str):
                        code = code.strip().upper()
                        if code.isascii() and code.isalpha() and 3 <= len(code) <= 4:
                            pair[key] = code
            try:
                record = FincraRate.model_validate(item)
            except ValidationError as exc:
                raise invalid(
                    f"Invalid rate at row {index}",
                    row=index,
                    **pair,
                    errors=exc.errors(
                        include_input=False, include_context=False, include_url=False
                    ),
                ) from None
            pair = {"base_currency": record.baseCurrency, "quote_currency": record.quoteCurrency}
            if record.baseCurrency == record.quoteCurrency:
                raise invalid("Source and target currency must differ", row=index, **pair)
            if record.price >= Decimal("1e16"):
                raise invalid("Price outside storage range", row=index, **pair)
            records.append(record)
        return records, paging
