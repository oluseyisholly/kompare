from __future__ import annotations

import re
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.adapters.giftcard.cardtonic import CardtonicAdapter
from app.core.logger import logger
from app.models.enums import GiftCardRateUnit, GiftCardType, MarketCategory, ProviderName, RawSourceType
from app.models.giftcard_rate import GiftCardRate
from app.repositories.asset import AssetRepository
from app.repositories.fetch_run import FetchRunRepository
from app.repositories.giftcard_rate import GiftCardRateRepository
from app.repositories.giftcard_variant import GiftCardVariantRepository
from app.repositories.provider import ProviderRepository
from app.repositories.raw_record import RawRecordRepository
from app.repositories.kyc import KycRepository


class CardtonicIngestionService:
    def __init__(
        self,
        db: Session,
        *,
        adapter: CardtonicAdapter,
        asset_repository: AssetRepository,
        provider_repository: ProviderRepository,
        fetch_run_repository: FetchRunRepository,
        raw_record_repository: RawRecordRepository,
        giftcard_variant_repository: GiftCardVariantRepository,
        giftcard_rate_repository: GiftCardRateRepository,
        kyc_repository: KycRepository,
    ) -> None:
        self.db = db
        self.adapter = adapter
        self.asset_repository = asset_repository
        self.provider_repository = provider_repository
        self.fetch_run_repository = fetch_run_repository
        self.raw_record_repository = raw_record_repository
        self.giftcard_variant_repository = giftcard_variant_repository
        self.giftcard_rate_repository = giftcard_rate_repository
        self.kyc_repository = kyc_repository

    async def ingest_kyc(self) -> dict[str, int]:
        run = self.fetch_run_repository.create_pending(ProviderName.CARDTONIC)
        try:
            async with httpx.AsyncClient() as client:
                document = await self.adapter.fetch_kyc_document(client=client)
            raw = self.raw_record_repository.create(
                provider=ProviderName.CARDTONIC, fetch_run_id=run.id,
                source_type=RawSourceType.HTML, source_url=self.adapter.kyc_url,
                payload=document, raw_text=document["content"],
            )
            count = self.kyc_repository.create_profile_with_levels(
                provider=ProviderName.CARDTONIC, source_url=self.adapter.kyc_url,
                fetch_run=run, raw_record=raw, kyc_document=document,
            )
            self.fetch_run_repository.mark_success(run, records_fetched=count)
            return {"fetch_run_id": run.id, "kyc_levels_created": count}
        except Exception as exc:
            self.db.rollback()
            self.fetch_run_repository.mark_failed(run, error_message=str(exc))
            raise

    async def ingest(self, *, include_top_cards: bool = True) -> dict[str, int]:
        fetch_run = self.fetch_run_repository.create_pending(ProviderName.CARDTONIC)

        try:
            provider = self.provider_repository.get_or_create_by_slug(
                slug=ProviderName.CARDTONIC.value,
                name="Cardtonic",
                description="Gift card platform integrated for gift card rate harvesting.",
                website_url=self.adapter.site_url,
                category=MarketCategory.GIFTCARD,
                has_adapter=True,
            )

            async with httpx.AsyncClient() as client:
                categories_payload = await self.adapter.fetch_categories(client=client)
                top_cards_payload = None
                if include_top_cards:
                    top_cards_payload = await self.adapter.fetch_top_cards(client=client)

                categories = categories_payload.get("data", [])
                categories_raw = self.raw_record_repository.create(
                    provider=ProviderName.CARDTONIC,
                    fetch_run_id=fetch_run.id,
                    source_type=RawSourceType.API,
                    source_url=self.adapter.categories_url,
                    payload=categories_payload,
                )

                raw_records_created = 1
                if include_top_cards and top_cards_payload is not None:
                    self.raw_record_repository.create(
                        provider=ProviderName.CARDTONIC,
                        fetch_run_id=fetch_run.id,
                        source_type=RawSourceType.API,
                        source_url=self.adapter.top_cards_url,
                        payload=top_cards_payload,
                    )
                    raw_records_created += 1

                variants_processed = 0
                rates_created = 0

                for category in categories:
                    asset = self.asset_repository.upsert(
                        code=self._asset_code(category),
                        name=self._asset_name(category),
                        category=MarketCategory.GIFTCARD,
                        metadata_json={
                            "avatar": category.get("avatar"),
                            "avatars": category.get("avatars"),
                            "source_provider": ProviderName.CARDTONIC.value,
                            "provider_category_id": category.get("_id"),
                        },
                    )

                    category_id = str(category.get("_id", "")).strip()
                    if not category_id:
                        continue

                    subcategories_payload = await self.adapter.fetch_subcategories(category_id, client=client)
                    subcategories_raw = self.raw_record_repository.create(
                        provider=ProviderName.CARDTONIC,
                        fetch_run_id=fetch_run.id,
                        source_type=RawSourceType.API,
                        source_url=self.adapter.subcategories_url(category_id),
                        payload=subcategories_payload,
                    )
                    raw_records_created += 1

                    created = self._persist_subcategories(
                        provider_id=provider.id,
                        asset_id=asset.id,
                        category=category,
                        subcategories=subcategories_payload.get("data", []),
                        fetch_run_id=fetch_run.id,
                        raw_record_id=subcategories_raw.id,
                    )
                    variants_processed += created["variants_processed"]
                    rates_created += created["rates_created"]

                self.fetch_run_repository.mark_success(
                    fetch_run,
                    records_fetched=variants_processed,
                )

                return {
                    "fetch_run_id": fetch_run.id,
                    "categories_processed": len(categories),
                    "variants_processed": variants_processed,
                    "rates_created": rates_created,
                    "raw_records_created": raw_records_created,
                    "categories_raw_record_id": categories_raw.id,
                }
        except Exception as exc:
            self.db.rollback()
            self.fetch_run_repository.mark_failed(fetch_run, error_message=str(exc))
            logger.exception("Cardtonic ingestion failed")
            raise

    async def ingest_market_data(self) -> dict[str, int]:
        return await self.ingest(include_top_cards=True)

    def _persist_subcategories(
        self,
        *,
        provider_id: int,
        asset_id: int,
        category: dict[str, Any],
        subcategories: list[dict[str, Any]],
        fetch_run_id: int,
        raw_record_id: int,
    ) -> dict[str, int]:
        rates: list[GiftCardRate] = []

        for subcategory in subcategories:
            external_id = str(subcategory.get("_id", "")).strip()
            if not external_id:
                continue

            minimum_face_value, maximum_face_value = self._resolve_face_value_range(subcategory)
            region = self._resolve_region(subcategory, category)
            source_currency, source_currency_resolution = self._resolve_source_currency(
                subcategory=subcategory,
                region=region,
            )
            card_type = self._resolve_card_type(subcategory)

            variant = self.giftcard_variant_repository.upsert(
                provider_id=provider_id,
                asset_id=asset_id,
                external_id=external_id,
                name=str(subcategory.get("name") or ""),
                brand_name=self._asset_name(category),
                region=region,
                source_currency=source_currency,
                card_type=card_type,
                minimum_face_value=minimum_face_value,
                maximum_face_value=maximum_face_value,
                terms_of_transaction=subcategory.get("termsOfTransaction"),
                is_active=bool(subcategory.get("isActive", True)),
                metadata_json={
                    "category_id": category.get("_id"),
                    "category_name": category.get("name"),
                    "description": subcategory.get("description"),
                    "tags": subcategory.get("tag"),
                    "sample_image": subcategory.get("sampleImage"),
                    "partner_rate": subcategory.get("partnerRate"),
                    "user_info": subcategory.get("userInfo"),
                    "currency_symbol": subcategory.get("currency"),
                    "source_currency_resolution": source_currency_resolution,
                },
            )

            rate_value = self._resolve_ngn_rate(subcategory)
            if rate_value is None:
                logger.warning("Skipping Cardtonic rate for variant=%s because NGN rate is missing", variant.name)
                continue

            rates.append(
                GiftCardRate(
                    provider_id=provider_id,
                    giftcard_variant_id=variant.id,
                    fetch_run_id=fetch_run_id,
                    raw_record_id=raw_record_id,
                    rate_value=rate_value,
                    rate_currency="NGN",
                    rate_unit=GiftCardRateUnit.PER_FACE_VALUE_UNIT,
                    source_currency=source_currency,
                    minimum_face_value=minimum_face_value,
                    maximum_face_value=maximum_face_value,
                    is_active=bool(subcategory.get("isActive", True)),
                    captured_at=datetime.now(UTC),
                    metadata_json={
                        "raw_rate": subcategory.get("rate"),
                        "rates": subcategory.get("rates"),
                        "partner_rate": subcategory.get("partnerRate"),
                        "approval_delay": subcategory.get("approvalDelay"),
                        "auto_approve": subcategory.get("autoApprove"),
                        "auto_assign": subcategory.get("autoAssign"),
                        "auto_reject": subcategory.get("autoReject"),
                        "minimum_acceptable_amount": subcategory.get("minimumAcceptableAmount"),
                    },
                )
            )

        created_rates = self.giftcard_rate_repository.create_many(rates)
        return {
            "variants_processed": len(subcategories),
            "rates_created": created_rates,
        }

    def _asset_name(self, category: dict[str, Any]) -> str:
        name = str(category.get("name") or "").strip()
        cleaned = re.sub(r"\s+gift\s+card$", "", name, flags=re.IGNORECASE).strip()
        return cleaned or name

    def _asset_code(self, category: dict[str, Any]) -> str:
        normalized = self._asset_name(category).upper()
        normalized = normalized.replace("&", "AND")
        normalized = re.sub(r"[^A-Z0-9]+", "_", normalized)
        normalized = re.sub(r"_+", "_", normalized).strip("_")
        return normalized or "UNKNOWN_GIFTCARD"

    def _resolve_region(self, subcategory: dict[str, Any], category: dict[str, Any]) -> str | None:
        name = str(subcategory.get("name") or "")
        brand_name = self._asset_name(category)
        if not name or not brand_name:
            return None

        prefix = name.split(brand_name, 1)[0].strip()
        prefix = prefix.replace("Gift Card", "").strip(" -")
        return prefix or None

    def _resolve_source_currency(
        self,
        *,
        subcategory: dict[str, Any],
        region: str | None,
    ) -> tuple[str | None, str | None]:
        currency = str(subcategory.get("currency") or "").strip().upper()
        mapping = {
            "$": "USD",
            "USD": "USD",
            "£": "GBP",
            "GBP": "GBP",
            "€": "EUR",
            "EUR": "EUR",
            "C$": "CAD",
            "CAD": "CAD",
            "A$": "AUD",
            "AUD": "AUD",
        }
        resolved = mapping.get(currency) or (currency if len(currency) == 3 else None)
        if resolved:
            return resolved, "payload"

        name_currency = self._infer_currency_from_name(str(subcategory.get("name") or ""))
        if name_currency:
            return name_currency, "name_inference"

        region_currency = self._infer_currency_from_region(region)
        if region_currency:
            return region_currency, "region_inference"

        return None, None

    def _infer_currency_from_name(self, name: str) -> str | None:
        normalized = name.upper()

        direct_markers = {
            " USD ": "USD",
            "(USD": "USD",
            " USD)": "USD",
            " GBP ": "GBP",
            "(GBP": "GBP",
            " GBP)": "GBP",
            " EUR ": "EUR",
            "(EUR": "EUR",
            " EUR)": "EUR",
            " CAD ": "CAD",
            "(CAD": "CAD",
            " CAD)": "CAD",
            " AUD ": "AUD",
            "(AUD": "AUD",
            " AUD)": "AUD",
        }
        padded = f" {normalized} "
        for marker, code in direct_markers.items():
            if marker in padded:
                return code

        region_markers = {
            "USA": "USD",
            "US ": "USD",
            "UNITED STATES": "USD",
            "UK": "GBP",
            "UNITED KINGDOM": "GBP",
            "EU": "EUR",
            "EUROPE": "EUR",
            "GERMANY": "EUR",
            "FRANCE": "EUR",
            "ITALY": "EUR",
            "SPAIN": "EUR",
            "NETHERLANDS": "EUR",
            "CANADA": "CAD",
            "AUSTRALIA": "AUD",
        }
        for marker, code in region_markers.items():
            if marker in normalized:
                return code

        return None

    def _infer_currency_from_region(self, region: str | None) -> str | None:
        if not region:
            return None

        normalized = region.strip().upper()
        mapping = {
            "USA": "USD",
            "US": "USD",
            "UNITED STATES": "USD",
            "UK": "GBP",
            "UNITED KINGDOM": "GBP",
            "EU": "EUR",
            "EUROPE": "EUR",
            "GERMANY": "EUR",
            "FRANCE": "EUR",
            "ITALY": "EUR",
            "SPAIN": "EUR",
            "NETHERLANDS": "EUR",
            "CANADA": "CAD",
            "AUSTRALIA": "AUD",
        }
        return mapping.get(normalized)

    def _resolve_card_type(self, subcategory: dict[str, Any]) -> GiftCardType:
        tags = [str(tag).upper() for tag in (subcategory.get("tag") or [])]
        if "ECODE" in tags:
            return GiftCardType.ECODE
        if "PHYSICAL" in tags:
            return GiftCardType.PHYSICAL
        return GiftCardType.OTHER

    def _resolve_face_value_range(self, subcategory: dict[str, Any]) -> tuple[Decimal | None, Decimal | None]:
        name = str(subcategory.get("name") or "")
        minimum = self._to_decimal(subcategory.get("minimumAcceptableAmount"))
        maximum = None

        range_match = re.search(r"\((\d+)\s*-\s*(\d+)\)", name)
        if range_match:
            minimum = minimum or Decimal(range_match.group(1))
            maximum = Decimal(range_match.group(2))
            return minimum, maximum

        lower_bound_match = re.search(r"\((\d+)\s+and\s+above\)", name, flags=re.IGNORECASE)
        if lower_bound_match:
            minimum = minimum or Decimal(lower_bound_match.group(1))
            return minimum, None

        single_value_match = re.search(r"\((\d+)\s+[a-zA-Z ]+\)", name)
        if single_value_match and minimum is None:
            minimum = Decimal(single_value_match.group(1))

        return minimum, maximum

    def _resolve_ngn_rate(self, subcategory: dict[str, Any]) -> Decimal | None:
        rates = subcategory.get("rates") or {}
        ngn_rate = rates.get("ngn")
        if ngn_rate is not None:
            return self._to_decimal(ngn_rate)
        return self._to_decimal(subcategory.get("rate"))

    def _to_decimal(self, value: Any) -> Decimal | None:
        if value in (None, ""):
            return None
        return Decimal(str(value))
