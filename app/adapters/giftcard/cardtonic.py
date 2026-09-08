from __future__ import annotations

from typing import Any

import httpx

from app.core.config import CARDTONIC_API_ENV, CARDTONIC_BASE_URL, CARDTONIC_SITE_URL, CARDTONIC_KYC_URL
from app.adapters.giftcard.cardtonic_kyc import parse_kyc_article
from app.utils.scraper import get_soup
from app.models.enums import MarketCategory, ProviderName
from app.utils.http_client import get_json


class CardtonicAdapter:
    name = ProviderName.CARDTONIC.value
    category = MarketCategory.GIFTCARD.value
    categories_path = "/v1/trades/pbc/cards/cats"
    top_cards_path = "/v1/trades/pbc/cards/top"

    def __init__(
        self,
        base_url: str = CARDTONIC_BASE_URL,
        site_url: str = CARDTONIC_SITE_URL,
        api_env: str = CARDTONIC_API_ENV,
        kyc_url: str = CARDTONIC_KYC_URL,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.site_url = site_url.rstrip("/")
        self.api_env = api_env
        self.kyc_url = kyc_url

    async def fetch_kyc_document(self, *, client: httpx.AsyncClient | None = None) -> dict[str, Any]:
        soup = await get_soup(self.kyc_url, client=client, timeout=20)
        return parse_kyc_article(soup)

    @property
    def categories_url(self) -> str:
        return self._url(self.categories_path)

    @property
    def top_cards_url(self) -> str:
        return self._url(self.top_cards_path)

    def subcategories_url(self, category_id: str) -> str:
        return self._url(f"{self.categories_path}/{category_id}/subs")

    async def fetch_categories(self, *, client: httpx.AsyncClient | None = None) -> dict[str, Any]:
        return await get_json(
            self.categories_url,
            headers=self._headers(),
            client=client,
        )

    async def fetch_subcategories(
        self,
        category_id: str,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> dict[str, Any]:
        return await get_json(
            self.subcategories_url(category_id),
            headers=self._headers(),
            client=client,
        )

    async def fetch_top_cards(self, *, client: httpx.AsyncClient | None = None) -> dict[str, Any]:
        return await get_json(
            self.top_cards_url,
            headers=self._headers(),
            client=client,
        )

    def _headers(self) -> dict[str, str]:
        return {
            "Accept": "application/json",
            "Origin": self.site_url,
            "Referer": f"{self.site_url}/",
            "X-CT-ENV": self.api_env,
        }

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"
