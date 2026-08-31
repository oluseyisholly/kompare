from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx
from bs4 import Tag

from app.core.config import (
    BUSHA_API_KEY,
    BUSHA_BASE_URL,
    BUSHA_KYC_IDENTITY_URL,
    BUSHA_KYC_LIMITS_URL,
)
from app.models.enums import MarketCategory, ProviderName
from app.utils.http_client import get_json
from app.utils.scraper import get_browser_headers, render_browser_soup


class BushaAdapter:
    name = ProviderName.BUSHA.value
    category = MarketCategory.CRYPTO.value
    pairs_path = "/v1/pairs"

    def __init__(
        self,
        base_url: str = BUSHA_BASE_URL,
        api_key: str | None = BUSHA_API_KEY,
        kyc_identity_url: str = BUSHA_KYC_IDENTITY_URL,
        kyc_limits_url: str = BUSHA_KYC_LIMITS_URL,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.kyc_identity_url = kyc_identity_url
        self.kyc_limits_url = kyc_limits_url

    @property
    def pairs_url(self) -> str:
        return self._url(self.pairs_path)

    @property
    def kyc_url(self) -> str:
        return self.kyc_limits_url

    async def fetch_pairs(self, *, client: httpx.AsyncClient | None = None) -> dict[str, Any]:
        return await get_json(
            self.pairs_url,
            headers=self._headers(),
            client=client,
        )

    async def fetch_kyc_document(
        self,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> dict[str, Any]:
        del client
        identity_soup = await render_browser_soup(
            self.kyc_identity_url,
            headers=self._browser_headers(),
            timeout=45.0,
            wait_after_load_ms=4000,
        )
        limits_soup = await render_browser_soup(
            self.kyc_limits_url,
            headers=self._browser_headers(),
            timeout=45.0,
            wait_after_load_ms=4000,
        )

        title = self._clean_text(limits_soup.select_one("h1")) or self._clean_text(
            identity_soup.select_one("h1")
        )
        updated_text = (
            self._clean_text(limits_soup.find("time"))
            or self._clean_text(limits_soup.select_one(".article__meta"))
            or self._clean_text(identity_soup.find("time"))
            or self._clean_text(identity_soup.select_one(".article__meta"))
        )
        identity_article = identity_soup.select_one("article") or identity_soup.select_one("main")
        limits_article = limits_soup.select_one("article") or limits_soup.select_one("main")
        levels = self._merge_levels(
            self._extract_identity_levels(identity_article),
            self._extract_limit_levels(limits_article),
        )

        return {
            "title": title,
            "updated_at": self._parse_support_datetime(updated_text),
            "content": "\n\n".join(
                part for part in [
                    self._clean_text(identity_article),
                    self._clean_text(limits_article),
                ] if part
            ),
            "levels": levels,
            "metadata_json": {
                "identity_source_url": self.kyc_identity_url,
                "limits_source_url": self.kyc_limits_url,
            },
        }

    def _extract_identity_levels(self, article: Tag | None) -> list[dict[str, Any]]:
        if article is None:
            return []

        text = article.get_text("\n", strip=True)
        levels: list[dict[str, Any]] = []
        mapping = [
            ("Level 0", "Confirm your email address."),
            ("Level 1", "Confirm your mobile number and basic personal details."),
            ("Level 2", "Submit a valid means of identification (BVN, Government issued ID)."),
            ("Level 3", "Submit proof of residential address."),
        ]

        for index, (level_name, description) in enumerate(mapping, start=1):
            if level_name in text:
                levels.append(
                    {
                        "level_name": level_name,
                        "description": description,
                        "requirements": [description],
                        "limit_reference": "kyc_level",
                        "exchange_limit_text": None,
                        "exchange_limit_period": None,
                        "fiat_deposit_limit": None,
                        "fiat_withdrawal_limit": None,
                        "crypto_deposit_limit": None,
                        "crypto_withdrawal_limit": None,
                        "notes": None,
                        "metadata_json": {},
                    }
                )

        return levels

    def _extract_limit_levels(self, article: Tag | None) -> list[dict[str, Any]]:
        if article is None:
            return []

        text = article.get_text("\n", strip=True)
        normalized = " ".join(text.split())
        levels: list[dict[str, Any]] = []
        level_configs = [
            (
                "Level 1",
                "unlimited crypto and fiat deposits",
                "no crypto or fiat withdrawals",
                "monthly",
            ),
            (
                "Level 2",
                "NGN 10,000,000",
                "NGN 10,000,000",
                "monthly",
            ),
            (
                "Level 3",
                "NGN 500,000,000",
                "NGN 500,000,000",
                "monthly",
            ),
        ]

        for level_name, deposit_limit, withdrawal_limit, period in level_configs:
            if level_name not in normalized:
                continue

            levels.append(
                {
                    "level_name": level_name,
                    "description": None,
                    "requirements": [],
                    "limit_reference": "deposit_withdrawal",
                    "exchange_limit_text": withdrawal_limit,
                    "exchange_limit_period": period,
                    "fiat_deposit_limit": deposit_limit,
                    "fiat_withdrawal_limit": withdrawal_limit,
                    "crypto_deposit_limit": "Unlimited" if "unlimited crypto" in deposit_limit.lower() else None,
                    "crypto_withdrawal_limit": "None" if "no crypto" in withdrawal_limit.lower() else None,
                    "notes": None,
                    "metadata_json": {"source": "limits_page"},
                }
            )

        return levels

    def _merge_levels(
        self,
        identity_levels: list[dict[str, Any]],
        limit_levels: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        merged: dict[str, dict[str, Any]] = {}

        for level in limit_levels:
            merged[level["level_name"]] = level

        for level in identity_levels:
            current = merged.get(level["level_name"], {}).copy()
            current.update({k: v for k, v in level.items() if v not in (None, [], {})})
            current.setdefault("level_name", level["level_name"])
            current.setdefault("requirements", level.get("requirements", []))
            current.setdefault("metadata_json", {})
            merged[level["level_name"]] = current

        return sorted(
            merged.values(),
            key=lambda item: self._level_rank(item.get("level_name")),
        )

    def _level_rank(self, value: str | None) -> int:
        if not value:
            return 999
        digits = "".join(ch for ch in value if ch.isdigit())
        return int(digits) if digits else 999

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _browser_headers(self) -> dict[str, str]:
        return get_browser_headers({"Referer": "https://support.busha.io/"})

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def _parse_support_datetime(self, value: str) -> datetime | None:
        if not value:
            return None

        cleaned = " ".join(value.split())
        for fmt in ("%B %d, %Y", "%B %d, %Y %H:%M", "%B %d, %Y %I:%M %p"):
            try:
                return datetime.strptime(cleaned, fmt).replace(tzinfo=UTC)
            except ValueError:
                continue
        return None

    def _clean_text(self, node: Tag | None) -> str:
        if node is None:
            return ""
        return " ".join(node.get_text(" ", strip=True).split())
