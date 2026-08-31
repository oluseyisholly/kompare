from __future__ import annotations

from sqlalchemy.orm import Session, joinedload

from app.models.enums import ProviderName
from app.models.provider_asset import ProviderAsset


class ProviderAssetRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_active_by_provider(self, provider: ProviderName) -> dict[str, ProviderAsset]:
        rows = (
            self.db.query(ProviderAsset)
            .options(joinedload(ProviderAsset.asset))
            .filter(
                ProviderAsset.provider == provider,
                ProviderAsset.is_active.is_(True),
            )
            .all()
        )
        return {row.provider_symbol: row for row in rows}

    def get_by_provider_and_symbol(
        self,
        provider: ProviderName,
        provider_symbol: str,
    ) -> ProviderAsset | None:
        return (
            self.db.query(ProviderAsset)
            .options(joinedload(ProviderAsset.asset))
            .filter(
                ProviderAsset.provider == provider,
                ProviderAsset.provider_symbol == provider_symbol,
            )
            .first()
        )

    def upsert(
        self,
        *,
        provider: ProviderName,
        asset_id: int,
        provider_symbol: str,
        provider_name: str | None = None,
        metadata_json: dict | None = None,
        is_active: bool = True,
    ) -> ProviderAsset:
        row = self.get_by_provider_and_symbol(provider, provider_symbol)
        if row is None:
            row = ProviderAsset(
                provider=provider,
                asset_id=asset_id,
                provider_symbol=provider_symbol,
                provider_name=provider_name,
                metadata_json=metadata_json,
                is_active=is_active,
            )
            self.db.add(row)
            self.db.commit()
            self.db.refresh(row)
            return row

        row.asset_id = asset_id
        row.provider_name = provider_name
        row.metadata_json = metadata_json
        row.is_active = is_active
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row
