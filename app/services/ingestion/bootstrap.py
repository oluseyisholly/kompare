from __future__ import annotations

import asyncio
from typing import Any

import httpx

from app.adapters.crypto.busha import BushaAdapter
from app.adapters.crypto.quidax import QuidaxAdapter
from app.core.database import SessionLocal
from app.core.focus_assets import FOCUS_ASSET_CODES
from app.core.logger import logger
from app.models.enums import MarketCategory, ProviderName
from app.repositories.asset import AssetRepository
from app.repositories.provider_asset import ProviderAssetRepository
from app.services.ingestion.focus import FocusAssetSelector


FOCUS_ASSET_NAMES: dict[str, str] = {
    "BTC": "Bitcoin",
    "USDT": "Tether",
    "ETH": "Ethereum",
    "XAUT": "Tether Gold",
    "USDC": "USD Coin",
    "TRX": "TRON",
    "DASH": "Dash",
    "LTC": "Litecoin",
    "XRP": "XRP",
    "SOL": "Solana",
    "QDX": "Quidax Token",
    "BNB": "BNB",
    "DOGE": "Dogecoin",
}

_bootstrap_tasks: set[asyncio.Task[None]] = set()


class BootstrapIngestionService:
    def __init__(
        self,
        *,
        asset_repository: AssetRepository,
        provider_asset_repository: ProviderAssetRepository,
        quidax_adapter: QuidaxAdapter,
        busha_adapter: BushaAdapter,
        focus_selector: FocusAssetSelector | None = None,
    ) -> None:
        self.asset_repository = asset_repository
        self.provider_asset_repository = provider_asset_repository
        self.quidax_adapter = quidax_adapter
        self.busha_adapter = busha_adapter
        self.focus_selector = focus_selector or FocusAssetSelector()

    async def run(self) -> dict[str, int]:
        assets_seeded = self.seed_focus_assets()

        async with httpx.AsyncClient() as client:
            quidax_markets = await self.quidax_adapter.fetch_markets(client=client)
            busha_pairs = await self.busha_adapter.fetch_pairs(client=client)

        quidax_provider_assets = self.sync_quidax_provider_assets(quidax_markets)
        busha_provider_assets = self.sync_busha_provider_assets(busha_pairs)

        return {
            "assets_seeded": assets_seeded,
            "quidax_provider_assets_synced": quidax_provider_assets,
            "busha_provider_assets_synced": busha_provider_assets,
        }

    async def run_provider(self, provider_slug: str) -> dict[str, int]:
        normalized = provider_slug.lower()
        assets_seeded = self.seed_focus_assets()

        async with httpx.AsyncClient() as client:
            if normalized == ProviderName.QUIDAX.value:
                quidax_markets = await self.quidax_adapter.fetch_markets(client=client)
                return {
                    "assets_seeded": assets_seeded,
                    "quidax_provider_assets_synced": self.sync_quidax_provider_assets(quidax_markets),
                    "busha_provider_assets_synced": 0,
                }

            if normalized == ProviderName.BUSHA.value:
                busha_pairs = await self.busha_adapter.fetch_pairs(client=client)
                return {
                    "assets_seeded": assets_seeded,
                    "quidax_provider_assets_synced": 0,
                    "busha_provider_assets_synced": self.sync_busha_provider_assets(busha_pairs),
                }

        raise ValueError(f"Unsupported bootstrap provider: {provider_slug}")

    def seed_focus_assets(self) -> int:
        created_or_updated = 0
        for code in sorted(FOCUS_ASSET_CODES):
            self.asset_repository.upsert(
                code=code,
                name=FOCUS_ASSET_NAMES.get(code, code),
                category=MarketCategory.CRYPTO,
                metadata_json=None,
                is_active=True,
            )
            created_or_updated += 1
        return created_or_updated

    def sync_quidax_provider_assets(self, payload: dict[str, Any]) -> int:
        synced = 0
        assets_by_code = self.asset_repository.get_by_codes(FOCUS_ASSET_CODES)

        for market in payload.get("data", []):
            base_code = str(market.get("base_unit", "")).upper()
            quote_code = str(market.get("quote_unit", "")).upper()
            if not self.focus_selector.should_use_pair(base_code=base_code, quote_code=quote_code):
                continue

            asset = assets_by_code.get(base_code)
            if asset is None:
                continue

            self.provider_asset_repository.upsert(
                provider=ProviderName.QUIDAX,
                asset_id=asset.id,
                provider_symbol=str(market.get("id", "")),
                provider_name=market.get("name") or asset.name,
                metadata_json={
                    "quote_unit": quote_code,
                    "base_unit": base_code,
                    "trading_rules": market.get("trading_rules", {}),
                    "filters": market.get("filters", {}),
                },
                is_active=True,
            )
            synced += 1

        return synced

    def sync_busha_provider_assets(self, payload: dict[str, Any]) -> int:
        synced = 0
        pairs = [
            pair
            for pair in payload.get("data", [])
            if self.focus_selector.should_use_pair(
                base_code=pair.get("base"),
                quote_code=pair.get("counter"),
            )
        ]
        assets_by_code = self.asset_repository.get_by_codes(pair.get("base", "") for pair in pairs)

        for pair in pairs:
            base_code = str(pair.get("base", "")).upper()
            quote_code = str(pair.get("counter", "")).upper()
            asset = assets_by_code.get(base_code)
            if asset is None:
                continue

            self.provider_asset_repository.upsert(
                provider=ProviderName.BUSHA,
                asset_id=asset.id,
                provider_symbol=str(pair.get("id", "")),
                provider_name=pair.get("base_currency_name") or asset.name,
                metadata_json={
                    "quote_unit": quote_code,
                    "quote_name": pair.get("counter_currency_name"),
                    "pair_type": pair.get("type"),
                    "is_buy_supported": pair.get("is_buy_supported"),
                    "is_sell_supported": pair.get("is_sell_supported"),
                    "base_decimal": pair.get("base_decimal"),
                    "counter_decimal": pair.get("counter_decimal"),
                    "min_buy_amount": pair.get("min_buy_amount"),
                    "min_sell_amount": pair.get("min_sell_amount"),
                    "max_buy_amount": pair.get("max_buy_amount"),
                    "max_sell_amount": pair.get("max_sell_amount"),
                    "percentage_change": pair.get("percentage_change"),
                },
                is_active=True,
            )
            synced += 1

        return synced


async def run_bootstrap_job(provider_slug: str | None = None) -> None:
    db = SessionLocal()
    try:
        service = BootstrapIngestionService(
            asset_repository=AssetRepository(db),
            provider_asset_repository=ProviderAssetRepository(db),
            quidax_adapter=QuidaxAdapter(),
            busha_adapter=BushaAdapter(),
            focus_selector=FocusAssetSelector(),
        )
        if provider_slug:
            result = await service.run_provider(provider_slug)
            logger.info(
                "Bootstrap ingestion completed for provider=%s result=%s",
                provider_slug,
                result,
            )
            return

        result = await service.run()
        logger.info("Bootstrap ingestion completed for all providers result=%s", result)
    except Exception:
        logger.exception("Bootstrap ingestion failed for provider=%s", provider_slug or "all")
    finally:
        db.close()


def launch_bootstrap_job(provider_slug: str | None = None) -> None:
    task = asyncio.create_task(run_bootstrap_job(provider_slug))
    _bootstrap_tasks.add(task)
    task.add_done_callback(_bootstrap_tasks.discard)
