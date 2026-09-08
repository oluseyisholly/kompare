from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.core.exceptions import BadRequestError
from app.core.exceptions import NotFoundError
from app.models.enums import GiftCardType, IngestionJobType, ProviderName
from app.models.ingestion_schedule import IngestionSchedule
from app.repositories.ingestion_schedule import IngestionScheduleRepository
from app.repositories.giftcard_rate import GiftCardRateRepository
from app.repositories.giftcard_variant import GiftCardVariantRepository
from app.repositories.kyc import KycRepository
from app.repositories.provider import ProviderRepository
from app.schemas.common import ApiResponse, PaginatedData, build_paginated_response
from app.schemas.giftcard import GiftCardRateRead, GiftCardVariantRead
from app.schemas.ingestion_schedule import IngestionScheduleRead, IngestionScheduleUpsert
from app.schemas.platform import (
    FetchRunRead,
    KycProfileCreate,
    KycProfileRead,
    PlatformAssetRead,
    PlatformQuoteRead,
    RawRecordRead,
)
from app.schemas.provider import ProviderRead, ProviderUpdate
from app.services.ingestion.bootstrap import launch_bootstrap_job


class ProviderService:
    def __init__(
        self,
        repository: ProviderRepository,
        ingestion_schedule_repository: IngestionScheduleRepository,
        kyc_repository: KycRepository,
        giftcard_variant_repository: GiftCardVariantRepository,
        giftcard_rate_repository: GiftCardRateRepository,
    ) -> None:
        self.repository = repository
        self.ingestion_schedule_repository = ingestion_schedule_repository
        self.kyc_repository = kyc_repository
        self.giftcard_variant_repository = giftcard_variant_repository
        self.giftcard_rate_repository = giftcard_rate_repository

    @staticmethod
    def _to_schema(provider) -> ProviderRead:
        return ProviderRead(
            id=provider.id,
            slug=provider.slug,
            name=provider.name,
            description=provider.description,
            logo_url=provider.logo_url,
            website_url=provider.website_url,
            category=provider.category.value,
            is_active=provider.is_active,
            has_adapter=provider.has_adapter,
            metadata_json=provider.metadata_json,
            created_at=provider.created_at,
            updated_at=provider.updated_at,
        )

    @staticmethod
    def _to_schedule_schema(schedule: IngestionSchedule) -> IngestionScheduleRead:
        return IngestionScheduleRead(
            id=schedule.id,
            provider_id=schedule.provider_id,
            provider_slug=schedule.provider.slug,
            job_type=schedule.job_type.value,
            interval_minutes=schedule.interval_minutes,
            is_enabled=schedule.is_enabled,
            next_run_at=schedule.next_run_at,
            last_run_at=schedule.last_run_at,
            notes=schedule.notes,
            metadata_json=schedule.metadata_json,
            created_at=schedule.created_at,
            updated_at=schedule.updated_at,
        )

    def _get_provider_or_raise(self, slug: str):
        provider = self.repository.get_by_slug(slug)
        if provider is None:
            raise NotFoundError(
                "Provider not found",
                data={"slug": slug},
            )
        return provider

    def _provider_name_or_404(self, provider: str) -> ProviderName:
        try:
            return ProviderName(provider.lower())
        except ValueError as exc:
            raise NotFoundError(
                "Provider not found",
                data={"provider": provider},
            ) from exc

    def _parse_job_type(self, job_type: str) -> IngestionJobType:
        try:
            return IngestionJobType(job_type.lower())
        except ValueError as exc:
            raise BadRequestError(
                "Invalid ingestion job type",
                data={
                    "job_type": job_type,
                    "allowed_values": [value.value for value in IngestionJobType],
                },
            ) from exc

    def _parse_giftcard_type(self, card_type: str | None) -> GiftCardType | None:
        if not card_type:
            return None
        try:
            return GiftCardType(card_type.lower())
        except ValueError as exc:
            raise BadRequestError(
                "Invalid gift card type",
                data={
                    "card_type": card_type,
                    "allowed_values": [value.value for value in GiftCardType],
                },
            ) from exc

    def list_providers(self) -> ApiResponse[list[ProviderRead]]:
        providers = self.repository.list_all()
        return ApiResponse(
            responseCode=200,
            message="Providers retrieved successfully",
            data=[self._to_schema(provider) for provider in providers],
        )

    def get_assets(self, provider: str, *, page: int, per_page: int) -> ApiResponse[PaginatedData[PlatformAssetRead]]:
        provider_enum = self._provider_name_or_404(provider)
        rows, total = self.repository.get_assets(provider_enum, page=page, per_page=per_page)
        items = [
            PlatformAssetRead(
                id=row.id,
                provider_symbol=row.provider_symbol,
                provider_name=row.provider_name,
                asset_code=row.asset.code,
                asset_name=row.asset.name,
                quote_unit=(row.metadata_json or {}).get("quote_unit"),
                is_active=row.is_active,
                metadata_json=row.metadata_json,
            )
            for row in rows
        ]
        return build_paginated_response(
            items=items,
            page=page,
            per_page=per_page,
            total=total,
            message="Provider assets retrieved successfully",
        )

    def get_quotes(self, provider: str, *, page: int, per_page: int) -> ApiResponse[PaginatedData[PlatformQuoteRead]]:
        provider_enum = self._provider_name_or_404(provider)
        rows, total = self.repository.get_quotes(provider_enum, page=page, per_page=per_page)
        items = [
            PlatformQuoteRead(
                id=row.id,
                provider_symbol=row.provider_asset.provider_symbol if row.provider_asset else None,
                asset_code=row.asset.code,
                base_currency=row.base_currency,
                quote_currency=row.quote_currency,
                quote_type=row.quote_type.value,
                buy_rate=row.buy_rate,
                sell_rate=row.sell_rate,
                mid_rate=row.mid_rate,
                market_price=row.market_price,
                captured_at=row.captured_at,
                last_seen_at=row.last_seen_at,
                superseded_at=row.superseded_at,
            )
            for row in rows
        ]
        return build_paginated_response(
            items=items,
            page=page,
            per_page=per_page,
            total=total,
            message="Provider quotes retrieved successfully",
        )

    def get_fetch_runs(self, provider: str, *, page: int, per_page: int) -> ApiResponse[PaginatedData[FetchRunRead]]:
        provider_enum = self._provider_name_or_404(provider)
        rows, total = self.repository.get_fetch_runs(provider_enum, page=page, per_page=per_page)
        items = [
            FetchRunRead(
                id=row.id,
                provider=row.provider.value,
                status=row.status.value,
                started_at=row.started_at,
                finished_at=row.finished_at,
                error_message=row.error_message,
                records_fetched=row.records_fetched,
                metadata_json=row.metadata_json,
            )
            for row in rows
        ]
        return build_paginated_response(
            items=items,
            page=page,
            per_page=per_page,
            total=total,
            message="Provider fetch runs retrieved successfully",
        )

    def get_raw_records(self, provider: str, *, page: int, per_page: int) -> ApiResponse[PaginatedData[RawRecordRead]]:
        provider_enum = self._provider_name_or_404(provider)
        rows, total = self.repository.get_raw_records(provider_enum, page=page, per_page=per_page)
        items = [
            RawRecordRead(
                id=row.id,
                provider=row.provider.value,
                fetch_run_id=row.fetch_run_id,
                source_type=row.source_type.value,
                source_url=row.source_url,
                external_id=row.external_id,
                payload=row.payload,
                raw_text=row.raw_text,
                fetched_at=row.fetched_at,
            )
            for row in rows
        ]
        return build_paginated_response(
            items=items,
            page=page,
            per_page=per_page,
            total=total,
            message="Provider raw records retrieved successfully",
        )

    def get_kyc_profiles(self, provider: str, *, page: int, per_page: int) -> ApiResponse[PaginatedData[KycProfileRead]]:
        provider_enum = self._provider_name_or_404(provider)
        rows, total = self.repository.get_kyc_profiles(provider_enum, page=page, per_page=per_page)
        items = [
            KycProfileRead(
                id=row.id,
                provider=row.provider.value,
                title=row.title,
                source_url=row.source_url,
                source_updated_at=row.source_updated_at,
                fetched_at=row.fetched_at,
                levels=sorted(row.levels, key=lambda level: level.rank),
            )
            for row in rows
        ]
        return build_paginated_response(
            items=items,
            page=page,
            per_page=per_page,
            total=total,
            message="Provider KYC profiles retrieved successfully",
        )

    def get_giftcard_variants(
        self,
        slug: str,
        *,
        page: int,
        per_page: int,
        asset_code: str | None = None,
        source_currency: str | None = None,
        region: str | None = None,
        card_type: str | None = None,
    ) -> ApiResponse[PaginatedData[GiftCardVariantRead]]:
        provider = self._get_provider_or_raise(slug)
        card_type_enum = self._parse_giftcard_type(card_type)
        rows, total = self.repository.get_giftcard_variants(
            provider.id,
            page=page,
            per_page=per_page,
            asset_code=asset_code,
            source_currency=source_currency,
            region=region,
            card_type=card_type_enum,
        )
        items = []
        for row in rows:
            latest_rate = self.giftcard_rate_repository.get_latest_for_variant(giftcard_variant_id=row.id)
            items.append(
                GiftCardVariantRead(
                    id=row.id,
                    provider_id=row.provider_id,
                    asset_id=row.asset_id,
                    asset_code=row.asset.code,
                    asset_name=row.asset.name,
                    external_id=row.external_id,
                    name=row.name,
                    brand_name=row.brand_name,
                    region=row.region,
                    source_currency=row.source_currency,
                    card_type=row.card_type.value if row.card_type else None,
                    minimum_face_value=row.minimum_face_value,
                    maximum_face_value=row.maximum_face_value,
                    terms_of_transaction=row.terms_of_transaction,
                    is_active=row.is_active,
                    latest_rate_ngn=latest_rate.rate_value if latest_rate else None,
                    latest_rate_captured_at=latest_rate.captured_at if latest_rate else None,
                    metadata_json=row.metadata_json,
                )
            )

        return build_paginated_response(
            items=items,
            page=page,
            per_page=per_page,
            total=total,
            message="Provider gift card variants retrieved successfully",
        )

    def get_giftcard_rates(
        self,
        slug: str,
        *,
        page: int,
        per_page: int,
        asset_code: str | None = None,
        source_currency: str | None = None,
        region: str | None = None,
        card_type: str | None = None,
    ) -> ApiResponse[PaginatedData[GiftCardRateRead]]:
        provider = self._get_provider_or_raise(slug)
        card_type_enum = self._parse_giftcard_type(card_type)
        rows, total = self.repository.get_giftcard_rates(
            provider.id,
            page=page,
            per_page=per_page,
            asset_code=asset_code,
            source_currency=source_currency,
            region=region,
            card_type=card_type_enum,
        )
        items = [
            GiftCardRateRead(
                id=row.id,
                provider_id=row.provider_id,
                giftcard_variant_id=row.giftcard_variant_id,
                asset_code=row.giftcard_variant.asset.code,
                asset_name=row.giftcard_variant.asset.name,
                variant_name=row.giftcard_variant.name,
                region=row.giftcard_variant.region,
                source_currency=row.source_currency,
                card_type=row.giftcard_variant.card_type.value if row.giftcard_variant.card_type else None,
                rate_value=row.rate_value,
                rate_currency=row.rate_currency,
                rate_unit=row.rate_unit.value,
                last_seen_at=row.last_seen_at,
                superseded_at=row.superseded_at,
                minimum_face_value=row.minimum_face_value,
                maximum_face_value=row.maximum_face_value,
                is_active=row.is_active,
                captured_at=row.captured_at,
                metadata_json=row.metadata_json,
            )
            for row in rows
        ]
        return build_paginated_response(
            items=items,
            page=page,
            per_page=per_page,
            total=total,
            message="Provider gift card rates retrieved successfully",
        )

    def create_kyc_profile(
        self,
        provider: str,
        payload: KycProfileCreate,
    ) -> ApiResponse[KycProfileRead]:
        provider_enum = self._provider_name_or_404(provider)
        if not payload.levels:
            raise BadRequestError(
                "At least one KYC level is required",
                data={"provider": provider},
            )

        profile = self.kyc_repository.create_manual_profile(
            provider=provider_enum,
            title=payload.title,
            source_url=payload.source_url,
            source_updated_at=payload.source_updated_at,
            fetched_at=payload.fetched_at,
            levels=[level.dict() for level in payload.levels],
        )

        return ApiResponse(
            responseCode=201,
            message="Provider KYC profile created successfully",
            data=KycProfileRead(
                id=profile.id,
                provider=profile.provider.value,
                title=profile.title,
                source_url=profile.source_url,
                source_updated_at=profile.source_updated_at,
                fetched_at=profile.fetched_at,
                levels=sorted(profile.levels, key=lambda level: level.rank),
            ),
        )

    def get_provider(self, slug: str) -> ApiResponse[ProviderRead]:
        provider = self._get_provider_or_raise(slug)

        return ApiResponse(
            responseCode=200,
            message="Provider retrieved successfully",
            data=self._to_schema(provider),
        )

    def update_provider(self, slug: str, payload: ProviderUpdate) -> ApiResponse[ProviderRead]:
        provider = self._get_provider_or_raise(slug)

        updated = self.repository.update(provider, **payload.dict(exclude_unset=True))
        return ApiResponse(
            responseCode=200,
            message="Provider updated successfully",
            data=self._to_schema(updated),
        )

    async def trigger_bootstrap(self, slug: str | None = None) -> ApiResponse[dict]:
        if slug is not None:
            provider = self._get_provider_or_raise(slug)
            if not provider.has_adapter:
                raise BadRequestError(
                    "Provider does not have an adapter configured",
                    data={"slug": slug},
                )
            launch_bootstrap_job(provider.slug)
            return ApiResponse(
                responseCode=202,
                message="Provider bootstrap started",
                data={"provider": provider.slug, "status": "accepted"},
            )

        launch_bootstrap_job()
        return ApiResponse(
            responseCode=202,
            message="Bootstrap started for supported providers",
            data={"provider": "all", "status": "accepted"},
        )

    def list_ingestion_schedules(self, slug: str) -> ApiResponse[list[IngestionScheduleRead]]:
        provider = self._get_provider_or_raise(slug)
        schedules = self.ingestion_schedule_repository.list_by_provider_id(provider.id)
        return ApiResponse(
            responseCode=200,
            message="Ingestion schedules retrieved successfully",
            data=[self._to_schedule_schema(schedule) for schedule in schedules],
        )

    def upsert_ingestion_schedule(
        self,
        slug: str,
        job_type: str,
        payload: IngestionScheduleUpsert,
    ) -> ApiResponse[IngestionScheduleRead]:
        provider = self._get_provider_or_raise(slug)
        job_type_enum = self._parse_job_type(job_type)
        existing = self.ingestion_schedule_repository.get_by_provider_id_and_job_type(provider.id, job_type_enum)

        next_run_at = payload.next_run_at
        if payload.is_enabled and next_run_at is None:
            base_time = existing.last_run_at if existing and existing.last_run_at else datetime.now(UTC)
            next_run_at = base_time + timedelta(minutes=payload.interval_minutes)
        if not payload.is_enabled:
            next_run_at = None

        fields = {
            "interval_minutes": payload.interval_minutes,
            "is_enabled": payload.is_enabled,
            "next_run_at": next_run_at,
            "notes": payload.notes,
        }

        if existing is None:
            schedule = IngestionSchedule(
                provider_id=provider.id,
                job_type=job_type_enum,
                **fields,
            )
            saved = self.ingestion_schedule_repository.create(schedule)
        else:
            saved = self.ingestion_schedule_repository.update(existing, **fields)

        return ApiResponse(
            responseCode=200,
            message="Ingestion schedule saved successfully",
            data=self._to_schedule_schema(saved),
        )
