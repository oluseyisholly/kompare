from __future__ import annotations

import asyncio
import hashlib
import json
import time
import uuid
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from app.core.config import TBAY_BASE_URL, TBAY_CLIENT_VERSION, TBAY_SIGNING_SALT, TBAY_SITE_URL
from app.core.exceptions import AppError


class TbayResponseError(AppError):
    def __init__(self, message: str, *, code: str):
        super().__init__(message, status_code=502, error_code="tbay_response_error", data={"api_code": code})


class TbayPaginationError(TbayResponseError):
    """A catalog traversal that can be retried from page one."""


class TbayAdapter:
    """Public calculator transport. Pricing normalization belongs to ingestion.

    Offer responses are sanitized; nested account information is not retained.
    No assumption is made that an advertised price is an unconditional payout.
    """

    name = "tbay"
    category = "giftcard"

    def __init__(self, base_url: str = TBAY_BASE_URL, site_url: str = TBAY_SITE_URL,
                 version: str = TBAY_CLIENT_VERSION, signing_salt: str = TBAY_SIGNING_SALT,
                 timeout: float = 20.0):
        self.base_url = base_url.rstrip("/")
        self.site_url = site_url.rstrip("/")
        self.version = version
        self.signing_salt = signing_salt
        self.timeout = timeout
        self.device_id = uuid.uuid4().hex
        self._offset_ms = 0
        self._synced_at: float | None = None
        self._clock_lock = asyncio.Lock()

    def source_url(self, code: str) -> str:
        return f"{self.base_url}/api?code={code}"

    async def _post(self, code: str, payload: dict, client: httpx.AsyncClient) -> Any:
        request_time = str(int(time.time() * 1000) + self._offset_ms)
        sign = hashlib.md5(
            f"{code}{request_time}{self.signing_salt}h5".encode(), usedforsecurity=False,
        ).hexdigest()
        fields = {"code": code, "client": "h5", "version": self.version,
                  "subsidiaryCode": "tbay000000001", "json": json.dumps(payload)}
        response = await client.post(
            self.source_url(code), files={key: (None, value) for key, value in fields.items()},
            headers={"Accept": "application/json", "Accept-Language": "en", "channel": "h5",
                     "Origin": self.site_url, "Referer": f"{self.site_url}/",
                     "requestTime": request_time, "deviceId": self.device_id, "sign": sign},
            timeout=self.timeout,
        )
        response.raise_for_status()
        try:
            body = response.json()
        except ValueError as exc:
            raise TbayResponseError("Tbay returned invalid JSON", code=code) from exc
        if not isinstance(body, dict) or str(body.get("errorCode")) != "0" or "data" not in body:
            raise TbayResponseError("Tbay rejected the request or returned an invalid envelope", code=code)
        return body["data"]

    async def _request(self, code: str, payload: dict, client: httpx.AsyncClient | None) -> Any:
        if client is None:
            async with httpx.AsyncClient() as owned:
                return await self._request(code, payload, owned)
        async with self._clock_lock:
            if self._synced_at is None or time.monotonic() - self._synced_at > 300:
                before = int(time.time() * 1000)
                timestamp = await self._post("600000", {}, client)
                try:
                    server_ms = int(timestamp["serverTimestamp"])
                    if server_ms <= 0:
                        raise ValueError("Invalid timestamp")
                except (TypeError, KeyError, ValueError) as exc:
                    raise TbayResponseError("Tbay returned an invalid server timestamp", code="600000") from exc
                self._offset_ms = server_ms - (before + int(time.time() * 1000)) // 2
                self._synced_at = time.monotonic()
        return await self._post(code, payload, client)

    @staticmethod
    def _list(data: Any, code: str) -> list[dict[str, Any]]:
        if not isinstance(data, list) or any(not isinstance(row, dict) for row in data):
            raise TbayResponseError("Tbay returned an invalid list", code=code)
        return data

    async def fetch_categories(self, *, client: httpx.AsyncClient | None = None) -> list[dict]:
        return self._list(await self._request("625350", {"type": "0", "status": "1", "buy": 1}, client), "625350")

    async def fetch_currencies(self, category_id: str, *, client: httpx.AsyncClient | None = None) -> list[dict]:
        if not category_id.strip():
            raise ValueError("category_id is required")
        return self._list(await self._request("806513", {
            "giftcardSell": 1, "kind": "", "giftcardType": category_id,
        }, client), "806513")

    async def fetch_points_rate(self, currency: str = "NGN", *, client: httpx.AsyncClient | None = None) -> dict:
        data = await self._request("650102", {"symbol": "Points", "referCurrency": currency.upper()}, client)
        if not isinstance(data, dict) or "mid" not in data:
            raise TbayResponseError("Tbay returned an invalid Points rate", code="650102")
        try:
            value = Decimal(str(data["mid"]))
            if not value.is_finite() or value <= 0:
                raise ValueError()
        except (InvalidOperation, ValueError) as exc:
            raise TbayResponseError("Tbay returned a non-positive or invalid Points rate", code="650102") from exc
        return data

    async def fetch_offers(self, category_id: str, currency: str, *,
                           client: httpx.AsyncClient | None = None,
                           page_size: int = 6, max_pages: int = 200,
                           attempts: int = 3) -> list[dict]:
        if attempts < 1:
            raise ValueError("attempts must be positive")
        for attempt in range(1, attempts + 1):
            try:
                return await self._fetch_offers_once(category_id, currency, client=client,
                                                     page_size=page_size, max_pages=max_pages)
            except TbayPaginationError as exc:
                exc.data.update(category_id=category_id, currency=currency, attempt=attempt)
                if attempt == attempts:
                    raise
                await asyncio.sleep(0.5 * attempt)
        raise AssertionError("Unreachable")

    async def _fetch_offers_once(self, category_id: str, currency: str, *,
                                client: httpx.AsyncClient | None,
                                page_size: int, max_pages: int) -> list[dict]:
        """Collect every page or raise; never return a silently truncated catalog."""
        if not category_id.strip() or not currency.strip() or not 1 <= page_size <= 100 or max_pages < 1:
            raise ValueError("Category, currency, and valid pagination bounds are required")
        if client is None:
            async with httpx.AsyncClient() as owned:
                return await self._fetch_offers_once(category_id, currency, client=owned,
                                               page_size=page_size, max_pages=max_pages)
        offers: dict[str, dict] = {}
        for page in range(1, max_pages + 1):
            data = await self._request("806206", {
                "giftcardType": category_id, "type": 0, "tradeCurrency": currency.upper(),
                "start": page, "limit": page_size,
                "orderColumn": "comprehensive_sort_value", "orderDir": "desc",
            }, client)
            if not isinstance(data, dict):
                raise TbayResponseError("Invalid Tbay offer page", code="806206")
            rows = self._list(data.get("list"), "806206")
            try:
                total = int(data["totalCount"])
                pages = int(data["totalPage"])
                if total < 0 or pages < 0 or (total > 0 and pages < 1):
                    raise ValueError()
            except (KeyError, TypeError, ValueError) as exc:
                raise TbayResponseError("Invalid Tbay pagination", code="806206") from exc
            previous_count = len(offers)
            for row in rows:
                key = row.get("code")
                if not isinstance(key, str) or not key or row.get("giftcardType") != category_id or row.get("tradeCurrency") != currency.upper():
                    raise TbayResponseError("Invalid Tbay offer identity", code="806206")
                offers[key] = self._sanitize_offer(row)
            if page >= pages:
                if len(offers) != total:
                    error = TbayPaginationError(
                        f"Incomplete Tbay catalog: category={category_id}, currency={currency}, "
                        f"page={page}/{pages}, unique_offers={len(offers)}, reported_total={total}", code="806206")
                    error.data.update(page=page, total_pages=pages, unique_offers=len(offers), reported_total=total)
                    raise error
                return list(offers.values())
            if len(offers) == previous_count:
                raise TbayPaginationError(
                    f"Tbay pagination made no progress: category={category_id}, currency={currency}, page={page}", code="806206")
        raise TbayResponseError("Tbay offer page limit exceeded", code="806206")

    @staticmethod
    def _sanitize_offer(row: dict) -> dict:
        # Explicit allowlist keeps unrelated seller-account fields out of raw storage.
        fields = ("code", "userId", "giftcardType", "tradeCurrency", "tradeCoin",
                  "originRate", "discount", "minTrade", "maxTrade", "fixTrade", "tagList",
                  "tag", "explain", "status", "paymentName", "deliverType", "giftcardAttribute",
                  "referenceAmount", "referenceDefaultCurrency", "referenceCardCurrency",
                  "defaultCurrencyMarketRate", "defaultCurrencyMarketPrice", "defaultCurrencySymbol",
                  "vipPremiumPrice", "currencySymbol", "updateDatetime")
        result = {key: row[key] for key in fields if key in row}
        ticket = row.get("raisePointTicket")
        if isinstance(ticket, dict):
            result["raisePointTicket"] = {k: ticket[k] for k in ("name", "type", "rate", "amount", "endDatetime") if k in ticket}
        return result
