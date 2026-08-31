from fastapi import APIRouter, Depends, Query
from app.dependencies import get_platform_service
from app.dependencies.auth import require_admin
from app.models.user import User
from app.schemas.common import ApiResponse, PaginatedData
from app.schemas.platform import (
    FetchRunRead,
    KycProfileCreate,
    KycProfileRead,
    PlatformAssetRead,
    PlatformQuoteRead,
    RawRecordRead,
)
from app.services.platform import PlatformService

router = APIRouter(prefix="/platforms", tags=["platforms"])


@router.get("/", response_model=ApiResponse[list[str]])
def list_platforms() -> ApiResponse[list[str]]:
    return PlatformService.list_platforms()


@router.get("/{provider}/assets", response_model=ApiResponse[PaginatedData[PlatformAssetRead]])
def get_platform_assets(
    provider: str,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    service: PlatformService = Depends(get_platform_service),
) -> ApiResponse[PaginatedData[PlatformAssetRead]]:
    return service.get_assets(provider, page=page, per_page=per_page)


@router.get("/{provider}/quotes", response_model=ApiResponse[PaginatedData[PlatformQuoteRead]])
def get_platform_quotes(
    provider: str,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    service: PlatformService = Depends(get_platform_service),
) -> ApiResponse[PaginatedData[PlatformQuoteRead]]:
    return service.get_quotes(provider, page=page, per_page=per_page)


@router.get("/{provider}/fetch-runs", response_model=ApiResponse[PaginatedData[FetchRunRead]])
def get_platform_fetch_runs(
    provider: str,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    service: PlatformService = Depends(get_platform_service),
) -> ApiResponse[PaginatedData[FetchRunRead]]:
    return service.get_fetch_runs(provider, page=page, per_page=per_page)


@router.get("/{provider}/raw-records", response_model=ApiResponse[PaginatedData[RawRecordRead]])
def get_platform_raw_records(
    provider: str,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    service: PlatformService = Depends(get_platform_service),
) -> ApiResponse[PaginatedData[RawRecordRead]]:
    return service.get_raw_records(provider, page=page, per_page=per_page)


@router.get("/{provider}/kyc", response_model=ApiResponse[PaginatedData[KycProfileRead]])
def get_platform_kyc(
    provider: str,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    service: PlatformService = Depends(get_platform_service),
) -> ApiResponse[PaginatedData[KycProfileRead]]:
    return service.get_kyc_profiles(provider, page=page, per_page=per_page)


@router.post("/{provider}/kyc", response_model=ApiResponse[KycProfileRead], status_code=201)
def create_platform_kyc(
    provider: str,
    payload: KycProfileCreate,
    service: PlatformService = Depends(get_platform_service),
    current_user: User = Depends(require_admin),
) -> ApiResponse[KycProfileRead]:
    del current_user
    return service.create_kyc_profile(provider, payload)
