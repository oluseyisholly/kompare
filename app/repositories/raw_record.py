from __future__ import annotations

from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from app.models.enums import ProviderName, RawSourceType
from app.models.raw_record import RawRecord


class RawRecordRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(
        self,
        *,
        provider: ProviderName,
        fetch_run_id: int,
        source_type: RawSourceType,
        source_url: str,
        payload: dict,
        raw_text: str | None = None,
    ) -> RawRecord:
        raw_record = RawRecord(
            provider=provider,
            fetch_run_id=fetch_run_id,
            source_type=source_type,
            source_url=source_url,
            payload=jsonable_encoder(payload),
            raw_text=raw_text,
        )
        self.db.add(raw_record)
        self.db.commit()
        self.db.refresh(raw_record)
        return raw_record
