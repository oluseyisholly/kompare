from fastapi import APIRouter, Depends, Query

from app.dependencies.auth import require_admin
from app.dependencies.providers import get_provider_service
from app.schemas.auth import AuthenticatedUser
from app.schemas.common import ApiResponse, PaginatedData
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
from app.services.provider import ProviderService

router = APIRouter(prefix="/providers", tags=["providers"])


@router.get("/", response_model=ApiResponse[list[ProviderRead]])
def list_providers(
    service: ProviderService = Depends(get_provider_service),
) -> ApiResponse[list[ProviderRead]]:
    return service.list_providers()


@router.get("/overview", response_model=ApiResponse[PaginatedData[ProviderOverviewRead]])
def list_provider_overview(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    search: str | None = Query(default=None),
    category: str | None = Query(default=None),
    status: str | None = Query(default=None),
    service: ProviderService = Depends(get_provider_service),
) -> ApiResponse[PaginatedData[ProviderOverviewRead]]:
    return service.list_provider_overview(
        page=page,
        per_page=per_page,
        search=search,
        category=category,
        status=status,
    )


@router.post("/metrics/refresh", response_model=ApiResponse[dict])
def refresh_all_provider_metrics(
    service: ProviderService = Depends(get_provider_service),
    current_user: AuthenticatedUser = Depends(require_admin),
) -> ApiResponse[dict]:
    del current_user
    return service.refresh_all_provider_metrics()


@router.get("/{slug}/crypto/assets", response_model=ApiResponse[PaginatedData[PlatformAssetRead]])
def get_provider_crypto_assets(
    slug: str,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    service: ProviderService = Depends(get_provider_service),
) -> ApiResponse[PaginatedData[PlatformAssetRead]]:
    return service.get_assets(slug, page=page, per_page=per_page)


@router.get(
    "/{slug}/giftcards/variants", response_model=ApiResponse[PaginatedData[GiftCardVariantRead]]
)
def get_provider_giftcard_variants(
    slug: str,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    asset_code: str | None = Query(default=None),
    source_currency: str | None = Query(default=None),
    region: str | None = Query(default=None),
    card_type: str | None = Query(default=None),
    service: ProviderService = Depends(get_provider_service),
) -> ApiResponse[PaginatedData[GiftCardVariantRead]]:
    return service.get_giftcard_variants(
        slug,
        page=page,
        per_page=per_page,
        asset_code=asset_code,
        source_currency=source_currency,
        region=region,
        card_type=card_type,
    )


@router.get("/{slug}/giftcards/rates", response_model=ApiResponse[PaginatedData[GiftCardRateRead]])
def get_provider_giftcard_rates(
    slug: str,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    asset_code: str | None = Query(default=None),
    source_currency: str | None = Query(default=None),
    region: str | None = Query(default=None),
    card_type: str | None = Query(default=None),
    service: ProviderService = Depends(get_provider_service),
) -> ApiResponse[PaginatedData[GiftCardRateRead]]:
    return service.get_giftcard_rates(
        slug,
        page=page,
        per_page=per_page,
        asset_code=asset_code,
        source_currency=source_currency,
        region=region,
        card_type=card_type,
    )


@router.get("/{slug}/crypto/quotes", response_model=ApiResponse[PaginatedData[PlatformQuoteRead]])
def get_provider_crypto_quotes(
    slug: str,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    service: ProviderService = Depends(get_provider_service),
) -> ApiResponse[PaginatedData[PlatformQuoteRead]]:
    return service.get_quotes(slug, page=page, per_page=per_page)


@router.get("/{slug}/fetch-runs", response_model=ApiResponse[PaginatedData[FetchRunRead]])
def get_provider_fetch_runs(
    slug: str,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    service: ProviderService = Depends(get_provider_service),
) -> ApiResponse[PaginatedData[FetchRunRead]]:
    return service.get_fetch_runs(slug, page=page, per_page=per_page)


@router.get("/{slug}/raw-records", response_model=ApiResponse[PaginatedData[RawRecordRead]])
def get_provider_raw_records(
    slug: str,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    service: ProviderService = Depends(get_provider_service),
    current_user: AuthenticatedUser = Depends(require_admin),
) -> ApiResponse[PaginatedData[RawRecordRead]]:
    return service.get_raw_records(slug, page=page, per_page=per_page)


@router.get("/{slug}/kyc", response_model=ApiResponse[PaginatedData[KycProfileRead]])
def get_provider_kyc(
    slug: str,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    service: ProviderService = Depends(get_provider_service),
) -> ApiResponse[PaginatedData[KycProfileRead]]:
    return service.get_kyc_profiles(slug, page=page, per_page=per_page)


@router.post("/{slug}/kyc", response_model=ApiResponse[KycProfileRead], status_code=201)
def create_provider_kyc(
    slug: str,
    payload: KycProfileCreate,
    service: ProviderService = Depends(get_provider_service),
    current_user: AuthenticatedUser = Depends(require_admin),
) -> ApiResponse[KycProfileRead]:
    del current_user
    return service.create_kyc_profile(slug, payload)


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
    current_user: AuthenticatedUser = Depends(require_admin),
) -> ApiResponse[ProviderRead]:
    del current_user
    return service.update_provider(slug, payload)


@router.post("/{slug}/metrics/refresh", response_model=ApiResponse[ProviderOverviewRead])
def refresh_provider_metrics(
    slug: str,
    service: ProviderService = Depends(get_provider_service),
    current_user: AuthenticatedUser = Depends(require_admin),
) -> ApiResponse[ProviderOverviewRead]:
    del current_user
    return service.refresh_provider_metrics(slug)


@router.post("/bootstrap", response_model=ApiResponse[dict], status_code=202)
async def trigger_all_provider_bootstrap(
    service: ProviderService = Depends(get_provider_service),
    current_user: AuthenticatedUser = Depends(require_admin),
) -> ApiResponse[dict]:
    del current_user
    return await service.trigger_bootstrap()


@router.post("/{slug}/bootstrap", response_model=ApiResponse[dict], status_code=202)
async def trigger_provider_bootstrap(
    slug: str,
    service: ProviderService = Depends(get_provider_service),
    current_user: AuthenticatedUser = Depends(require_admin),
) -> ApiResponse[dict]:
    del current_user
    return await service.trigger_bootstrap(slug)


@router.post("/{slug}/ingestion-runs/{job_type}", response_model=ApiResponse[dict], status_code=202)
async def trigger_provider_ingestion_run(
    slug: str,
    job_type: str,
    include_kyc: bool = Query(default=False),
    service: ProviderService = Depends(get_provider_service),
    current_user: AuthenticatedUser = Depends(require_admin),
) -> ApiResponse[dict]:
    del current_user
    return service.trigger_ingestion_run(slug, job_type, include_kyc=include_kyc)


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
    current_user: AuthenticatedUser = Depends(require_admin),
) -> ApiResponse[IngestionScheduleRead]:
    del current_user
    return service.upsert_ingestion_schedule(slug, job_type, payload)


@router.get("/{slug}/ingestion-jobs/{job_id}", response_model=ApiResponse[dict])
def get_ingestion_job(
    slug: str,
    job_id: int,
    service: ProviderService = Depends(get_provider_service),
    current_user: AuthenticatedUser = Depends(require_admin),
):
    from app.core.exceptions import NotFoundError
    from app.models.ingestion_job import IngestionJob

    row = (
        service.repository.db.query(IngestionJob)
        .filter_by(id=job_id, provider_slug=None if slug == "all" else slug)
        .one_or_none()
    )
    if row is None:
        raise NotFoundError("Ingestion job not found")
    return ApiResponse(
        responseCode=200,
        message="Ingestion job retrieved",
        data={
            "id": row.id,
            "provider": row.provider_slug,
            "job_type": row.job_type,
            "status": row.status,
            "attempts": row.attempts,
            "queued_at": row.queued_at,
            "finished_at": row.finished_at,
            "error_message": row.error_message,
        },
    )
