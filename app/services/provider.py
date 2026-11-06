from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.core.exceptions import BadRequestError, NotFoundError
from app.models.enums import GiftCardType, IngestionJobType, MarketCategory, ProviderName
from app.models.ingestion_schedule import IngestionSchedule
from app.models.provider_metric import ProviderMetric
from app.repositories.giftcard_rate import GiftCardRateRepository
from app.repositories.giftcard_variant import GiftCardVariantRepository
from app.repositories.ingestion_schedule import IngestionScheduleRepository
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
from app.schemas.provider import ProviderOverviewRead, ProviderRead, ProviderUpdate
from app.services.ingestion.bootstrap import launch_bootstrap_job
from app.services.ingestion.fx import FX_INGESTION_SERVICES, supported_fx_jobs
from app.services.ingestion.manual import launch_provider_ingestion_job
from app.services.provider_metric import ProviderMetricService


class ProviderService:
    def __init__(
        self,
        repository: ProviderRepository,
        ingestion_schedule_repository: IngestionScheduleRepository,
        kyc_repository: KycRepository,
        giftcard_variant_repository: GiftCardVariantRepository,
        giftcard_rate_repository: GiftCardRateRepository,
        provider_metric_service: ProviderMetricService,
    ) -> None:
        self.repository = repository
        self.ingestion_schedule_repository = ingestion_schedule_repository
        self.kyc_repository = kyc_repository
        self.giftcard_variant_repository = giftcard_variant_repository
        self.giftcard_rate_repository = giftcard_rate_repository
        self.provider_metric_service = provider_metric_service

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

    def _parse_category(self, category: str | None) -> MarketCategory | None:
        if not category:
            return None
        try:
            return MarketCategory(category.lower())
        except ValueError as exc:
            raise BadRequestError(
                "Invalid provider category",
                data={
                    "category": category,
                    "allowed_values": [value.value for value in MarketCategory],
                },
            ) from exc

    def _parse_status(self, status: str | None) -> bool | None:
        if not status:
            return None
        status_value = status.lower()
        if status_value == "active":
            return True
        if status_value == "inactive":
            return False
        raise BadRequestError(
            "Invalid provider status",
            data={"status": status, "allowed_values": ["active", "inactive"]},
        )

    @staticmethod
    def _to_overview_schema(provider, metric: ProviderMetric | None) -> ProviderOverviewRead:
        coverage_score = metric.coverage_score if metric is not None else 0
        data_source = (provider.metadata_json or {}).get("data_source") or f"{provider.name} Feed"
        return ProviderOverviewRead(
            id=provider.id,
            slug=provider.slug,
            name=provider.name,
            description=provider.description,
            logo_url=provider.logo_url,
            website_url=provider.website_url,
            category=provider.category.value,
            status="active" if provider.is_active else "inactive",
            is_active=provider.is_active,
            has_adapter=provider.has_adapter,
            average_rating=float(metric.average_rating)
            if metric is not None and metric.average_rating is not None
            else None,
            review_count=metric.review_count if metric is not None else 0,
            data_source=data_source,
            feed_health=metric.feed_health if metric is not None else "unknown",
            coverage_score=coverage_score,
            coverage_label=f"{coverage_score}/100",
            sync_mode="auto" if provider.has_adapter else "manual",
            last_synced_at=metric.last_synced_at if metric is not None else None,
        )

    def list_providers(self) -> ApiResponse[list[ProviderRead]]:
        providers = self.repository.list_all()
        return ApiResponse(
            responseCode=200,
            message="Providers retrieved successfully",
            data=[self._to_schema(provider) for provider in providers],
        )

    def list_provider_overview(
        self,
        *,
        page: int,
        per_page: int,
        search: str | None = None,
        category: str | None = None,
        status: str | None = None,
    ) -> ApiResponse[PaginatedData[ProviderOverviewRead]]:
        category_enum = self._parse_category(category)
        is_active = self._parse_status(status)
        rows, total = self.provider_metric_service.list_provider_overview(
            page=page,
            per_page=per_page,
            search=search,
            category=category_enum,
            is_active=is_active,
        )
        return build_paginated_response(
            items=[self._to_overview_schema(provider, metric) for provider, metric in rows],
            page=page,
            per_page=per_page,
            total=total,
            message="Provider overview retrieved successfully",
        )

    def refresh_all_provider_metrics(self) -> ApiResponse[dict]:
        metrics = self.provider_metric_service.refresh_all_providers()
        return ApiResponse(
            responseCode=200,
            message="Provider metrics refreshed successfully",
            data={"providers_refreshed": len(metrics)},
        )

    def refresh_provider_metrics(self, slug: str) -> ApiResponse[ProviderOverviewRead]:
        provider = self._get_provider_or_raise(slug)
        metric = self.provider_metric_service.refresh_provider(provider)
        return ApiResponse(
            responseCode=200,
            message="Provider metrics refreshed successfully",
            data=self._to_overview_schema(provider, metric),
        )

    def get_assets(
        self, provider: str, *, page: int, per_page: int
    ) -> ApiResponse[PaginatedData[PlatformAssetRead]]:
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

    def get_quotes(
        self, provider: str, *, page: int, per_page: int
    ) -> ApiResponse[PaginatedData[PlatformQuoteRead]]:
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

    def get_fetch_runs(
        self, provider: str, *, page: int, per_page: int
    ) -> ApiResponse[PaginatedData[FetchRunRead]]:
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

    def get_raw_records(
        self, provider: str, *, page: int, per_page: int
    ) -> ApiResponse[PaginatedData[RawRecordRead]]:
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

    def get_kyc_profiles(
        self, provider: str, *, page: int, per_page: int
    ) -> ApiResponse[PaginatedData[KycProfileRead]]:
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
        latest_rates = self.giftcard_rate_repository.get_latest_for_variants(
            [row.id for row in rows]
        )
        for row in rows:
            latest_rate = latest_rates.get(row.id)
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
                card_type=row.giftcard_variant.card_type.value
                if row.giftcard_variant.card_type
                else None,
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
            levels=[level.model_dump() for level in payload.levels],
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

        updated = self.repository.update(provider, **payload.model_dump(exclude_unset=True))
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
            job_id = launch_bootstrap_job(provider.slug, db=self.repository.db)
            return ApiResponse(
                responseCode=202,
                message="Provider bootstrap queued",
                data={
                    "provider": provider.slug,
                    "status": "accepted",
                    **({"job_id": job_id} if isinstance(job_id, int) else {}),
                },
            )

        job_id = launch_bootstrap_job(db=self.repository.db)
        return ApiResponse(
            responseCode=202,
            message="Bootstrap queued for supported providers",
            data={
                "provider": "all",
                "status": "accepted",
                **({"job_id": job_id} if isinstance(job_id, int) else {}),
            },
        )

    def trigger_ingestion_run(
        self,
        slug: str,
        job_type: str,
        *,
        include_kyc: bool,
    ) -> ApiResponse[dict]:
        provider = self._get_provider_or_raise(slug)
        if not provider.has_adapter:
            raise BadRequestError(
                "Provider does not have an adapter configured",
                data={"slug": slug},
            )

        job_type_enum = self._parse_job_type(job_type)
        if provider.slug in FX_INGESTION_SERVICES and job_type_enum not in supported_fx_jobs(
            provider.slug
        ):
            raise BadRequestError(
                "Ingestion job is not implemented for this FX provider",
                data={
                    "provider": provider.slug,
                    "job_type": job_type_enum.value,
                    "supported_jobs": sorted(job.value for job in supported_fx_jobs(provider.slug)),
                },
            )
        if (
            job_type_enum == IngestionJobType.CURRENCIES
            and provider.slug not in FX_INGESTION_SERVICES
        ):
            raise BadRequestError("Currency ingestion is not implemented for this provider")
        unsupported_jobs: dict[str, set[IngestionJobType]] = {
            "quidax": {IngestionJobType.FEES},
            "busha": {IngestionJobType.FEES},
            "cardtonic": {IngestionJobType.FEES},
            "tbay": {IngestionJobType.KYC, IngestionJobType.FEES},
            "stanbic": {IngestionJobType.KYC, IngestionJobType.FEES},
            "united_capital": {IngestionJobType.KYC, IngestionJobType.FEES},
        }
        if job_type_enum in unsupported_jobs.get(provider.slug, set()):
            raise BadRequestError(
                "Ingestion job is not implemented for this provider yet",
                data={
                    "provider": provider.slug,
                    "job_type": job_type_enum.value,
                },
            )

        if job_type_enum == IngestionJobType.FUND_DETAILS and provider.slug not in {
            "stanbic",
            "united_capital",
        }:
            raise BadRequestError(
                "Fund-details ingestion is supported only for Stanbic and United Capital"
            )

        if include_kyc and job_type_enum != IngestionJobType.MARKET_DATA:
            raise BadRequestError(
                "include_kyc can only be used with market_data ingestion",
                data={
                    "provider": provider.slug,
                    "job_type": job_type_enum.value,
                },
            )

        if include_kyc and (
            provider.slug in {"tbay", "stanbic", "united_capital"}
            or provider.slug in FX_INGESTION_SERVICES
        ):
            raise BadRequestError(
                "KYC ingestion is not implemented for this provider yet",
                data={"provider": provider.slug},
            )

        job_id = launch_provider_ingestion_job(
            db=self.repository.db,
            provider_slug=provider.slug,
            job_type=job_type_enum,
            include_kyc=include_kyc,
        )
        return ApiResponse(
            responseCode=202,
            message="Provider ingestion queued",
            data={
                "provider": provider.slug,
                "job_type": job_type_enum.value,
                "include_kyc": include_kyc,
                "status": "accepted",
                **({"job_id": job_id} if isinstance(job_id, int) else {}),
            },
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
        if provider.slug in FX_INGESTION_SERVICES and job_type_enum not in supported_fx_jobs(
            provider.slug
        ):
            raise BadRequestError(
                "Ingestion job is not implemented for this FX provider",
                data={
                    "provider": provider.slug,
                    "job_type": job_type_enum.value,
                    "supported_jobs": sorted(job.value for job in supported_fx_jobs(provider.slug)),
                },
            )
        if (
            job_type_enum == IngestionJobType.CURRENCIES
            and provider.slug not in FX_INGESTION_SERVICES
        ):
            raise BadRequestError("Currency ingestion is not implemented for this provider")
        existing = self.ingestion_schedule_repository.get_by_provider_id_and_job_type(
            provider.id, job_type_enum
        )
        if provider.slug == "united_capital" and job_type_enum not in {
            IngestionJobType.MARKET_DATA,
            IngestionJobType.FUND_DETAILS,
        }:
            raise BadRequestError("United Capital supports market_data and fund_details only")
        if provider.slug == "stanbic" and job_type_enum not in {
            IngestionJobType.MARKET_DATA,
            IngestionJobType.FUND_DETAILS,
        }:
            raise BadRequestError("Stanbic supports market_data and fund_details only")
        if job_type_enum == IngestionJobType.FUND_DETAILS and provider.slug not in {
            "stanbic",
            "united_capital",
        }:
            raise BadRequestError(
                "Fund-details ingestion is supported only for Stanbic and United Capital"
            )

        next_run_at = payload.next_run_at
        if payload.is_enabled and next_run_at is None:
            base_time = (
                existing.last_run_at if existing and existing.last_run_at else datetime.now(UTC)
            )
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
