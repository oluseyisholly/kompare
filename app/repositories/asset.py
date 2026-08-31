from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy.orm import Session

from app.models.asset import Asset
from app.models.enums import MarketCategory


class AssetRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_code(self, code: str) -> Asset | None:
        return self.db.query(Asset).filter(Asset.code == code.upper()).first()

    def get_by_codes(self, codes: Iterable[str]) -> dict[str, Asset]:
        normalized_codes = sorted({code.upper() for code in codes if code})
        if not normalized_codes:
            return {}

        rows = self.db.query(Asset).filter(Asset.code.in_(normalized_codes)).all()
        return {row.code.upper(): row for row in rows}

    def upsert(
        self,
        *,
        code: str,
        name: str,
        category: MarketCategory,
        metadata_json: dict | None = None,
        is_active: bool = True,
    ) -> Asset:
        normalized_code = code.upper()
        asset = self.get_by_code(normalized_code)
        if asset is None:
            asset = Asset(
                code=normalized_code,
                name=name,
                category=category,
                metadata_json=metadata_json,
                is_active=is_active,
            )
            self.db.add(asset)
            self.db.commit()
            self.db.refresh(asset)
            return asset

        asset.name = name
        asset.category = category
        asset.metadata_json = metadata_json
        asset.is_active = is_active
        self.db.add(asset)
        self.db.commit()
        self.db.refresh(asset)
        return asset
