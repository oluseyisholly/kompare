from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy.orm import Session

from app.models.asset import Asset


class AssetRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_codes(self, codes: Iterable[str]) -> dict[str, Asset]:
        normalized_codes = sorted({code.upper() for code in codes if code})
        if not normalized_codes:
            return {}

        rows = self.db.query(Asset).filter(Asset.code.in_(normalized_codes)).all()
        return {row.code.upper(): row for row in rows}
