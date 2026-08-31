from app.core.exceptions import BadRequestError, NotFoundError
from app.repositories.kyc import KycRepository
from app.models.enums import ProviderName
from app.repositories.platform import PlatformRepository
from app.schemas.common import ApiResponse, PaginatedData, build_pagination
from app.schemas.platform import (
    FetchRunRead,
    KycProfileCreate,
    KycProfileRead,
    PlatformAssetRead,
    PlatformQuoteRead,
    RawRecordRead,
)


class PlatformService:
    def __init__(self, repository: PlatformRepository, kyc_repository: KycRepository) -> None:
        self.repository = repository
        self.kyc_repository = kyc_repository

    def _provider_or_404(self, provider: str) -> ProviderName:
        try:
            return ProviderName(provider.lower())
        except ValueError as exc:
            raise NotFoundError(
                f"Unknown platform: {provider}",
                data={"provider": provider},
            ) from exc

    @staticmethod
    def list_platforms() -> ApiResponse[list[str]]:
        return ApiResponse(
            responseCode=200,
            message="Platforms retrieved successfully",
            data=[provider.value for provider in ProviderName],
        )

    def get_assets(self, provider: str, *, page: int, per_page: int) -> ApiResponse[PaginatedData[PlatformAssetRead]]:
        provider_enum = self._provider_or_404(provider)
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
        return ApiResponse(
            responseCode=200,
            message="Platform assets retrieved successfully",
            data=PaginatedData(items=items, pagination=build_pagination(page=page, per_page=per_page, total=total)),
        )

    def get_quotes(self, provider: str, *, page: int, per_page: int) -> ApiResponse[PaginatedData[PlatformQuoteRead]]:
        provider_enum = self._provider_or_404(provider)
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
            )
            for row in rows
        ]
        return ApiResponse(
            responseCode=200,
            message="Platform quotes retrieved successfully",
            data=PaginatedData(items=items, pagination=build_pagination(page=page, per_page=per_page, total=total)),
        )

    def get_fetch_runs(self, provider: str, *, page: int, per_page: int) -> ApiResponse[PaginatedData[FetchRunRead]]:
        provider_enum = self._provider_or_404(provider)
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
        return ApiResponse(
            responseCode=200,
            message="Platform fetch runs retrieved successfully",
            data=PaginatedData(items=items, pagination=build_pagination(page=page, per_page=per_page, total=total)),
        )

    def get_raw_records(self, provider: str, *, page: int, per_page: int) -> ApiResponse[PaginatedData[RawRecordRead]]:
        provider_enum = self._provider_or_404(provider)
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
        return ApiResponse(
            responseCode=200,
            message="Platform raw records retrieved successfully",
            data=PaginatedData(items=items, pagination=build_pagination(page=page, per_page=per_page, total=total)),
        )

    def get_kyc_profiles(self, provider: str, *, page: int, per_page: int) -> ApiResponse[PaginatedData[KycProfileRead]]:
        provider_enum = self._provider_or_404(provider)
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
        return ApiResponse(
            responseCode=200,
            message="Platform KYC profiles retrieved successfully",
            data=PaginatedData(items=items, pagination=build_pagination(page=page, per_page=per_page, total=total)),
        )

    def create_kyc_profile(
        self,
        provider: str,
        payload: KycProfileCreate,
    ) -> ApiResponse[KycProfileRead]:
        provider_enum = self._provider_or_404(provider)
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
            message="Platform KYC profile created successfully",
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
