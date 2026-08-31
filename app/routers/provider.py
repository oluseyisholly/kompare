from fastapi import APIRouter, Depends

from app.dependencies.auth import require_admin
from app.dependencies.providers import get_provider_service
from app.models.user import User
from app.schemas.common import ApiResponse
from app.schemas.ingestion_schedule import IngestionScheduleRead, IngestionScheduleUpsert
from app.schemas.provider import ProviderRead, ProviderUpdate
from app.services.provider import ProviderService

router = APIRouter(prefix="/providers", tags=["providers"])


@router.get("/", response_model=ApiResponse[list[ProviderRead]])
def list_providers(
    service: ProviderService = Depends(get_provider_service),
) -> ApiResponse[list[ProviderRead]]:
    return service.list_providers()


@router.get("/{slug}", response_model=ApiResponse[ProviderRead])
def get_provider(
    slug: str,
    service: ProviderService = Depends(get_provider_service),
) -> ApiResponse[ProviderRead]:
    return service.get_provider(slug)


@router.patch("/{slug}", response_model=ApiResponse[ProviderRead])
def update_provider(
    slug: str,
    payload: ProviderUpdate,
    service: ProviderService = Depends(get_provider_service),
) -> ApiResponse[ProviderRead]:
    return service.update_provider(slug, payload)


@router.get("/{slug}/ingestion-schedules", response_model=ApiResponse[list[IngestionScheduleRead]])
def list_provider_ingestion_schedules(
    slug: str,
    service: ProviderService = Depends(get_provider_service),
) -> ApiResponse[list[IngestionScheduleRead]]:
    return service.list_ingestion_schedules(slug)


@router.put(
    "/{slug}/ingestion-schedules/{job_type}",
    response_model=ApiResponse[IngestionScheduleRead],
)
def upsert_provider_ingestion_schedule(
    slug: str,
    job_type: str,
    payload: IngestionScheduleUpsert,
    service: ProviderService = Depends(get_provider_service),
    current_user: User = Depends(require_admin),
) -> ApiResponse[IngestionScheduleRead]:
    del current_user
    return service.upsert_ingestion_schedule(slug, job_type, payload)
