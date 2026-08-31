from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.adapters.crypto.busha import BushaAdapter
from app.core.logger import logger
from app.models.enums import ProviderName, QuoteType, RawSourceType
from app.models.fetch_run import FetchRun
from app.models.quote import Quote
from app.models.raw_record import RawRecord
from app.repositories.asset import AssetRepository
from app.repositories.fetch_run import FetchRunRepository
from app.repositories.kyc import KycRepository
from app.repositories.provider_asset import ProviderAssetRepository
from app.repositories.quote import QuoteRepository
from app.repositories.raw_record import RawRecordRepository
from app.services.ingestion.focus import FocusAssetSelector


class BushaIngestionService:
    def __init__(
        self,
        db: Session,
        *,
        adapter: BushaAdapter,
        asset_repository: AssetRepository,
        fetch_run_repository: FetchRunRepository,
        raw_record_repository: RawRecordRepository,
        provider_asset_repository: ProviderAssetRepository,
        quote_repository: QuoteRepository,
        kyc_repository: KycRepository,
        focus_selector: FocusAssetSelector | None = None,
    ) -> None:
        self.db = db
        self.adapter = adapter
        self.asset_repository = asset_repository
        self.fetch_run_repository = fetch_run_repository
        self.raw_record_repository = raw_record_repository
        self.provider_asset_repository = provider_asset_repository
        self.quote_repository = quote_repository
        self.kyc_repository = kyc_repository
        self.focus_selector = focus_selector or FocusAssetSelector()

    async def ingest(self, *, include_kyc: bool = True) -> dict[str, int]:
        fetch_run = self.fetch_run_repository.create_pending(ProviderName.BUSHA)

        try:
            async with httpx.AsyncClient() as client:
                pairs_payload = await self.adapter.fetch_pairs(client=client)
                kyc_document = None
                if include_kyc:
                    kyc_document = await self.adapter.fetch_kyc_document(client=client)

            pairs_raw = self.raw_record_repository.create(
                provider=ProviderName.BUSHA,
                fetch_run_id=fetch_run.id,
                source_type=RawSourceType.API,
                source_url=self.adapter.pairs_url,
                payload=pairs_payload,
            )

            filtered_pairs = self._filtered_pairs(pairs_payload)
            assets_by_code = self.asset_repository.get_by_codes(pair["base"] for pair in filtered_pairs)
            quotes_created = self._persist_pairs(
                pairs=filtered_pairs,
                assets_by_code=assets_by_code,
                fetch_run=fetch_run,
                raw_record=pairs_raw,
            )

            kyc_levels_created = 0
            if include_kyc and kyc_document:
                kyc_raw = self.raw_record_repository.create(
                    provider=ProviderName.BUSHA,
                    fetch_run_id=fetch_run.id,
                    source_type=RawSourceType.HTML,
                    source_url=self.adapter.kyc_url,
                    payload=kyc_document,
                    raw_text=kyc_document["content"],
                )
                kyc_levels_created = self.kyc_repository.create_profile_with_levels(
                    provider=ProviderName.BUSHA,
                    source_url=self.adapter.kyc_url,
                    fetch_run=fetch_run,
                    raw_record=kyc_raw,
                    kyc_document=kyc_document,
                )

            self.fetch_run_repository.mark_success(
                fetch_run,
                records_fetched=len(filtered_pairs),
            )

            return {
                "fetch_run_id": fetch_run.id,
                "pairs_processed": len(filtered_pairs),
                "quotes_created": quotes_created,
                "kyc_levels_created": kyc_levels_created,
            }
        except Exception as exc:
            self.db.rollback()
            self.fetch_run_repository.mark_failed(fetch_run, error_message=str(exc))
            logger.exception("Busha ingestion failed")
            raise

    async def ingest_market_data(self) -> dict[str, int]:
        return await self.ingest(include_kyc=False)

    async def ingest_kyc(self) -> dict[str, int]:
        fetch_run = self.fetch_run_repository.create_pending(ProviderName.BUSHA)

        try:
            async with httpx.AsyncClient() as client:
                kyc_document = await self.adapter.fetch_kyc_document(client=client)

            kyc_raw = self.raw_record_repository.create(
                provider=ProviderName.BUSHA,
                fetch_run_id=fetch_run.id,
                source_type=RawSourceType.HTML,
                source_url=self.adapter.kyc_url,
                payload=kyc_document,
                raw_text=kyc_document["content"],
            )
            kyc_levels_created = self.kyc_repository.create_profile_with_levels(
                provider=ProviderName.BUSHA,
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
            logger.exception("Busha KYC ingestion failed")
            raise

    def _filtered_pairs(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            pair
            for pair in payload.get("data", [])
            if self.focus_selector.should_use_pair(
                base_code=pair.get("base"),
                quote_code=pair.get("counter"),
            )
        ]

    def _persist_pairs(
        self,
        *,
        pairs: list[dict[str, Any]],
        assets_by_code: dict[str, Any],
        fetch_run: FetchRun,
        raw_record: RawRecord,
    ) -> int:
        quotes: list[Quote] = []

        for pair in pairs:
            base_code = str(pair.get("base", "")).upper()
            quote_code = str(pair.get("counter", "")).upper()
            asset = assets_by_code.get(base_code)
            if asset is None:
                logger.warning("Skipping Busha pair for missing asset %s", base_code)
                continue

            provider_asset = self.provider_asset_repository.upsert(
                provider=ProviderName.BUSHA,
                asset_id=asset.id,
                provider_symbol=str(pair.get("id", "")),
                provider_name=(pair.get("base_currency_name") or base_code),
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
            )

            buy_rate = self._to_decimal((pair.get("buy_price") or {}).get("amount"))
            sell_rate = self._to_decimal((pair.get("sell_price") or {}).get("amount"))
            mid_rate = self._midpoint(buy_rate, sell_rate)

            quotes.append(
                Quote(
                    provider=ProviderName.BUSHA,
                    asset_id=asset.id,
                    provider_asset_id=provider_asset.id,
                    fetch_run_id=fetch_run.id,
                    raw_record_id=raw_record.id,
                    quote_type=QuoteType.SPOT,
                    base_currency=base_code,
                    quote_currency=quote_code,
                    buy_rate=buy_rate,
                    sell_rate=sell_rate,
                    mid_rate=mid_rate,
                    market_price=mid_rate,
                    captured_at=datetime.now(UTC),
                    metadata_json={
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
                )
            )

        return self.quote_repository.create_many(quotes)

    def _midpoint(self, buy: Decimal | None, sell: Decimal | None) -> Decimal | None:
        if buy is None or sell is None:
            return None
        return (buy + sell) / Decimal("2")

    def _to_decimal(self, value: Any) -> Decimal | None:
        if value is None:
            return None
        return Decimal(str(value))
