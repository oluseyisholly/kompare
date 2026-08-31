from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.adapters.crypto.quidax import QuidaxAdapter
from app.core.logger import logger
from app.models.enums import ProviderName, QuoteType, RawSourceType
from app.models.fetch_run import FetchRun
from app.models.provider_asset import ProviderAsset
from app.models.quote import Quote
from app.models.raw_record import RawRecord
from app.repositories.fetch_run import FetchRunRepository
from app.repositories.kyc import KycRepository
from app.repositories.provider_asset import ProviderAssetRepository
from app.repositories.quote import QuoteRepository
from app.repositories.raw_record import RawRecordRepository
from app.services.ingestion.focus import FocusAssetSelector


class QuidaxIngestionService:
    def __init__(
        self,
        db: Session,
        *,
        adapter: QuidaxAdapter,
        fetch_run_repository: FetchRunRepository,
        raw_record_repository: RawRecordRepository,
        provider_asset_repository: ProviderAssetRepository,
        quote_repository: QuoteRepository,
        kyc_repository: KycRepository,
        focus_selector: FocusAssetSelector | None = None,
    ) -> None:
        self.db = db
        self.adapter = adapter
        self.fetch_run_repository = fetch_run_repository
        self.raw_record_repository = raw_record_repository
        self.provider_asset_repository = provider_asset_repository
        self.quote_repository = quote_repository
        self.kyc_repository = kyc_repository
        self.focus_selector = focus_selector or FocusAssetSelector()

    async def ingest(self, *, include_kyc: bool = True) -> dict[str, int]:
        fetch_run = self.fetch_run_repository.create_pending(ProviderName.QUIDAX)

        try:
            async with httpx.AsyncClient() as client:
                tickers_payload = await self.adapter.fetch_tickers(client=client)
                kyc_document = None
                if include_kyc:
                    kyc_document = await self.adapter.fetch_kyc_document(client=client)

            tickers_raw = self.raw_record_repository.create(
                provider=ProviderName.QUIDAX,
                fetch_run_id=fetch_run.id,
                source_type=RawSourceType.API,
                source_url=self.adapter.tickers_url,
                payload=tickers_payload,
            )

            provider_assets = self.provider_asset_repository.get_active_by_provider(ProviderName.QUIDAX)
            quotes_created = self._persist_tickers(
                tickers_payload=tickers_payload,
                fetch_run=fetch_run,
                raw_record=tickers_raw,
                provider_assets=provider_assets,
            )

            kyc_levels_created = 0
            if include_kyc and kyc_document:
                kyc_raw = self.raw_record_repository.create(
                    provider=ProviderName.QUIDAX,
                    fetch_run_id=fetch_run.id,
                    source_type=RawSourceType.HTML,
                    source_url=self.adapter.kyc_url,
                    payload=kyc_document,
                    raw_text=kyc_document["content"],
                )
                kyc_levels_created = self.kyc_repository.create_profile_with_levels(
                    provider=ProviderName.QUIDAX,
                    source_url=self.adapter.kyc_url,
                    fetch_run=fetch_run,
                    raw_record=kyc_raw,
                    kyc_document=kyc_document,
                )

            self.fetch_run_repository.mark_success(
                fetch_run,
                records_fetched=len(tickers_payload.get("data", {})),
            )

            return {
                "fetch_run_id": fetch_run.id,
                "markets_processed": len(provider_assets),
                "quotes_created": quotes_created,
                "kyc_levels_created": kyc_levels_created,
            }
        except Exception as exc:
            self.db.rollback()
            self.fetch_run_repository.mark_failed(fetch_run, error_message=str(exc))
            logger.exception("Quidax ingestion failed")
            raise

    async def ingest_market_data(self) -> dict[str, int]:
        return await self.ingest(include_kyc=False)

    async def ingest_kyc(self) -> dict[str, int]:
        fetch_run = self.fetch_run_repository.create_pending(ProviderName.QUIDAX)

        try:
            async with httpx.AsyncClient() as client:
                kyc_document = await self.adapter.fetch_kyc_document(client=client)

            kyc_raw = self.raw_record_repository.create(
                provider=ProviderName.QUIDAX,
                fetch_run_id=fetch_run.id,
                source_type=RawSourceType.HTML,
                source_url=self.adapter.kyc_url,
                payload=kyc_document,
                raw_text=kyc_document["content"],
            )
            kyc_levels_created = self.kyc_repository.create_profile_with_levels(
                provider=ProviderName.QUIDAX,
                source_url=self.adapter.kyc_url,
                fetch_run=fetch_run,
                raw_record=kyc_raw,
                kyc_document=kyc_document,
            )

            self.fetch_run_repository.mark_success(
                fetch_run,
                records_fetched=kyc_levels_created,
            )

            return {
                "fetch_run_id": fetch_run.id,
                "quotes_created": 0,
                "kyc_levels_created": kyc_levels_created,
            }
        except Exception as exc:
            self.db.rollback()
            self.fetch_run_repository.mark_failed(fetch_run, error_message=str(exc))
            logger.exception("Quidax KYC ingestion failed")
            raise

    def _persist_tickers(
        self,
        *,
        tickers_payload: dict[str, Any],
        fetch_run: FetchRun,
        raw_record: RawRecord,
        provider_assets: dict[str, ProviderAsset],
    ) -> int:
        quotes: list[Quote] = []

        for market_id, market_data in tickers_payload.get("data", {}).items():
            provider_asset = provider_assets.get(market_id)
            if provider_asset is None:
                logger.warning("Skipping ticker for unknown market %s", market_id)
                continue
            if not self.focus_selector.should_use_provider_asset(provider_asset):
                logger.info("Skipping non-focus asset ticker for market %s", market_id)
                continue

            ticker = market_data.get("ticker", {})
            quotes.append(
                Quote(
                    provider=ProviderName.QUIDAX,
                    asset_id=provider_asset.asset_id,
                    provider_asset_id=provider_asset.id,
                    fetch_run_id=fetch_run.id,
                    raw_record_id=raw_record.id,
                    quote_type=QuoteType.SPOT,
                    base_currency=self._base_currency(provider_asset),
                    quote_currency=self._quote_currency(provider_asset),
                    buy_rate=self._to_decimal(ticker.get("buy")),
                    sell_rate=self._to_decimal(ticker.get("sell")),
                    mid_rate=self._midpoint(ticker.get("buy"), ticker.get("sell")),
                    market_price=self._to_decimal(ticker.get("last")),
                    captured_at=self._from_epoch_ms(market_data.get("at")),
                    metadata_json={
                        "high": ticker.get("high"),
                        "low": ticker.get("low"),
                        "open": ticker.get("open"),
                        "volume": ticker.get("vol"),
                    },
                )
            )

        return self.quote_repository.create_many(quotes)

    def _base_currency(self, provider_asset: ProviderAsset) -> str:
        asset = provider_asset.asset
        return asset.code if asset is not None else provider_asset.provider_symbol[:3].upper()

    def _quote_currency(self, provider_asset: ProviderAsset) -> str:
        metadata_json = provider_asset.metadata_json or {}
        quote_unit = metadata_json.get("quote_unit")
        return str(quote_unit).upper() if quote_unit else ""

    def _midpoint(self, buy: Any, sell: Any) -> Decimal | None:
        buy_value = self._to_decimal(buy)
        sell_value = self._to_decimal(sell)
        if buy_value is None or sell_value is None:
            return None
        return (buy_value + sell_value) / Decimal("2")

    def _to_decimal(self, value: Any) -> Decimal | None:
        if value is None:
            return None
        return Decimal(str(value))

    def _from_epoch_ms(self, value: Any) -> datetime:
        if value is None:
            return datetime.now(UTC)
        return datetime.fromtimestamp(int(value) / 1000, tz=UTC)
