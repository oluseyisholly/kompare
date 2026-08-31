from fastapi import APIRouter, Depends

from app.dependencies.providers import get_provider_service
from app.schemas.common import ApiResponse
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
