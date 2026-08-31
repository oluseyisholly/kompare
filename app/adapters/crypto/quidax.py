from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx
from bs4 import Tag

from app.core.config import QUIDAX_API_KEY, QUIDAX_BASE_URL, QUIDAX_KYC_URL
from app.models.enums import MarketCategory, ProviderName
from app.utils.http_client import get_json
from app.utils.scraper import get_browser_headers, render_browser_soup


class QuidaxAdapter:
    name = ProviderName.QUIDAX.value
    category = MarketCategory.CRYPTO.value
    markets_path = "/exchange-open-api/api/v1/markets"
    tickers_path = "/exchange-open-api/api/v1/markets/tickers"

    def __init__(
        self,
        base_url: str = QUIDAX_BASE_URL,
        api_key: str | None = QUIDAX_API_KEY,
        kyc_url: str = QUIDAX_KYC_URL,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.kyc_url = kyc_url

    @property
    def markets_url(self) -> str:
        return self._url(self.markets_path)

    @property
    def tickers_url(self) -> str:
        return self._url(self.tickers_path)

    async def fetch_markets(self, *, client: httpx.AsyncClient | None = None) -> dict[str, Any]:
        return await get_json(
            self.markets_url,
            headers=self._headers(),
            client=client,
        )

    async def fetch_tickers(self, *, client: httpx.AsyncClient | None = None) -> dict[str, Any]:
        return await get_json(
            self.tickers_url,
            headers=self._headers(),
            client=client,
        )

    async def fetch_kyc_document(
        self,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> dict[str, Any]:
        """Scrape Quidax KYC content through the browser-based scraper path."""

        del client
        soup = await render_browser_soup(
            self.kyc_url,
            headers=self._browser_headers(),
            timeout=45.0,
            wait_after_load_ms=5000,
        )

        title = self._clean_text(soup.select_one("h1"))
        article_title = self._clean_text(
            soup.select_one(".article-title")
            or soup.select_one("[data-article-title]")
            or soup.select_one("main h1")
        )
        updated_text = self._clean_text(soup.find("time")) or self._clean_text(
            soup.select_one(".article-updated")
        )
        article = soup.select_one(".article-body") or soup.select_one("article")
        content = self._clean_text(article)

        levels = self._extract_kyc_levels(article)

        return {
            "title": article_title or title,
            "updated_at": self._parse_support_datetime(updated_text),
            "content": content,
            "levels": levels,
        }

    def _extract_kyc_levels(self, article: Tag | None) -> list[dict[str, Any]]:
        if article is None:
            return []

        children = [node for node in article.children if isinstance(node, Tag)]
        levels: list[dict[str, Any]] = []
        current: dict[str, Any] | None = None
        pending_section: str | None = None
        requirements: list[str] = []

        for child in children:
            text = self._clean_text(child)
            if not text:
                continue

            lowered = text.lower()
            if lowered.startswith("level 1") or lowered.startswith("level 2"):
                if current is not None:
                    current["requirements"] = requirements
                    current["exchange_limit_text"] = (
                        current["fiat_withdrawal_limit"]
                        or current["crypto_withdrawal_limit"]
                        or current["fiat_deposit_limit"]
                        or current["crypto_deposit_limit"]
                    )
                    levels.append(current)
                current = {
                    "level_name": text,
                    "description": None,
                    "requirements": [],
                    "limit_reference": "kyc_level",
                    "exchange_limit_text": None,
                    "exchange_limit_period": "daily",
                    "fiat_deposit_limit": "Unlimited",
                    "fiat_withdrawal_limit": None,
                    "crypto_deposit_limit": "Unlimited",
                    "crypto_withdrawal_limit": None,
                    "notes": None,
                    "metadata_json": {},
                }
                requirements = []
                pending_section = None
                continue

            if current is None:
                continue

            if "acceptable" in lowered and "verification" in lowered:
                pending_section = "requirements"
                continue
            if lowered == "fiat withdrawal limit":
                pending_section = "fiat_withdrawal_limit"
                continue
            if lowered == "crypto withdrawal limit":
                pending_section = "crypto_withdrawal_limit"
                continue

            if child.name == "ul":
                items = [self._clean_text(item) for item in child.find_all("li")]
                items = [item for item in items if item]
                if pending_section == "requirements":
                    requirements.extend(items)
                elif pending_section == "fiat_withdrawal_limit" and items:
                    current["fiat_withdrawal_limit"] = " ".join(items)
                elif pending_section == "crypto_withdrawal_limit" and items:
                    current["crypto_withdrawal_limit"] = " ".join(items)
                continue

            if pending_section == "requirements" and text.startswith("-"):
                requirements.append(text.lstrip("-").strip())
                continue

            if current["description"] is None and child.name in {"p", "div"}:
                current["description"] = text
                continue

            if pending_section == "fiat_withdrawal_limit" and "withdrawal limit" in lowered:
                current["fiat_withdrawal_limit"] = text
                continue
            if pending_section == "crypto_withdrawal_limit" and "withdrawal limit" in lowered:
                current["crypto_withdrawal_limit"] = text
                continue
            if lowered.startswith("ps:"):
                current["notes"] = text

        if current is not None:
            current["requirements"] = requirements
            current["exchange_limit_text"] = (
                current["fiat_withdrawal_limit"]
                or current["crypto_withdrawal_limit"]
                or current["fiat_deposit_limit"]
                or current["crypto_deposit_limit"]
            )
            levels.append(current)

        return levels

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _browser_headers(self) -> dict[str, str]:
        return get_browser_headers({"Referer": "https://support.quidax.io/"})

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def _parse_support_datetime(self, value: str) -> datetime | None:
        if not value:
            return None

        for fmt in ("%B %d, %Y %H:%M", "%B %d, %Y %I:%M %p"):
            try:
                return datetime.strptime(value, fmt).replace(tzinfo=UTC)
            except ValueError:
                continue
        return None

    def _clean_text(self, node: Tag | None) -> str:
        if node is None:
            return ""
        return " ".join(node.get_text(" ", strip=True).split())
