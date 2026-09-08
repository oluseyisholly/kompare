from fastapi import APIRouter, Depends
from fastapi import Query

from app.dependencies.auth import require_admin
from app.dependencies.providers import get_provider_service
from app.schemas.auth import AuthenticatedUser
from app.schemas.common import ApiResponse
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
from app.schemas.common import PaginatedData
from app.services.provider import ProviderService

router = APIRouter(prefix="/providers", tags=["providers"])


@router.get("/", response_model=ApiResponse[list[ProviderRead]])
def list_providers(
    service: ProviderService = Depends(get_provider_service),
) -> ApiResponse[list[ProviderRead]]:
    return service.list_providers()


@router.get("/{slug}/crypto/assets", response_model=ApiResponse[PaginatedData[PlatformAssetRead]])
def get_provider_crypto_assets(
    slug: str,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    service: ProviderService = Depends(get_provider_service),
) -> ApiResponse[PaginatedData[PlatformAssetRead]]:
    return service.get_assets(slug, page=page, per_page=per_page)


@router.get("/{slug}/giftcards/variants", response_model=ApiResponse[PaginatedData[GiftCardVariantRead]])
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
) -> ApiResponse[ProviderRead]:
    return service.update_provider(slug, payload)


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
