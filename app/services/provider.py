from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.core.exceptions import BadRequestError
from app.core.exceptions import NotFoundError
from app.models.enums import IngestionJobType
from app.models.ingestion_schedule import IngestionSchedule
from app.repositories.ingestion_schedule import IngestionScheduleRepository
from app.repositories.provider import ProviderRepository
from app.schemas.common import ApiResponse
from app.schemas.ingestion_schedule import IngestionScheduleRead, IngestionScheduleUpsert
from app.schemas.provider import ProviderRead, ProviderUpdate
from app.services.ingestion.bootstrap import launch_bootstrap_job


class ProviderService:
    def __init__(
        self,
        repository: ProviderRepository,
        ingestion_schedule_repository: IngestionScheduleRepository,
    ) -> None:
        self.repository = repository
        self.ingestion_schedule_repository = ingestion_schedule_repository

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

    def list_providers(self) -> ApiResponse[list[ProviderRead]]:
        providers = self.repository.list_all()
        return ApiResponse(
            responseCode=200,
            message="Providers retrieved successfully",
            data=[self._to_schema(provider) for provider in providers],
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

    def trigger_bootstrap(self, slug: str | None = None) -> ApiResponse[dict]:
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
