from __future__ import annotations

from app.core.exceptions import NotFoundError
from app.repositories.provider import ProviderRepository
from app.schemas.common import ApiResponse
from app.schemas.provider import ProviderRead, ProviderUpdate


class ProviderService:
    def __init__(self, repository: ProviderRepository) -> None:
        self.repository = repository

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

    def list_providers(self) -> ApiResponse[list[ProviderRead]]:
        providers = self.repository.list_all()
        return ApiResponse(
            responseCode=200,
            message="Providers retrieved successfully",
            data=[self._to_schema(provider) for provider in providers],
        )

    def get_provider(self, slug: str) -> ApiResponse[ProviderRead]:
        provider = self.repository.get_by_slug(slug)
        if provider is None:
            raise NotFoundError(
                "Provider not found",
                data={"slug": slug},
            )

        return ApiResponse(
            responseCode=200,
            message="Provider retrieved successfully",
            data=self._to_schema(provider),
        )

    def update_provider(self, slug: str, payload: ProviderUpdate) -> ApiResponse[ProviderRead]:
        provider = self.repository.get_by_slug(slug)
        if provider is None:
            raise NotFoundError(
                "Provider not found",
                data={"slug": slug},
            )

        updated = self.repository.update(provider, **payload.dict(exclude_unset=True))
        return ApiResponse(
            responseCode=200,
            message="Provider updated successfully",
            data=self._to_schema(updated),
        )
