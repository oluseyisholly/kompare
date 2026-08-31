from datetime import datetime

from sqlalchemy.orm import Session, joinedload

from app.models.enums import IngestionJobType
from app.models.ingestion_schedule import IngestionSchedule


class IngestionScheduleRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_by_provider_id(self, provider_id: int) -> list[IngestionSchedule]:
        return (
            self.db.query(IngestionSchedule)
            .options(joinedload(IngestionSchedule.provider))
            .filter(IngestionSchedule.provider_id == provider_id)
            .order_by(IngestionSchedule.job_type.asc(), IngestionSchedule.id.asc())
            .all()
        )

    def list_due(self, now: datetime) -> list[IngestionSchedule]:
        return (
            self.db.query(IngestionSchedule)
            .options(joinedload(IngestionSchedule.provider))
            .filter(
                IngestionSchedule.is_enabled.is_(True),
                IngestionSchedule.next_run_at.isnot(None),
                IngestionSchedule.next_run_at <= now,
            )
            .order_by(IngestionSchedule.next_run_at.asc(), IngestionSchedule.id.asc())
            .all()
        )

    def get_by_provider_id_and_job_type(
        self,
        provider_id: int,
        job_type: IngestionJobType,
    ) -> IngestionSchedule | None:
        return (
            self.db.query(IngestionSchedule)
            .filter(
                IngestionSchedule.provider_id == provider_id,
                IngestionSchedule.job_type == job_type,
            )
            .first()
        )

    def create(self, schedule: IngestionSchedule) -> IngestionSchedule:
        self.db.add(schedule)
        self.db.commit()
        self.db.refresh(schedule)
        return schedule

    def update(self, schedule: IngestionSchedule, **fields) -> IngestionSchedule:
        for key, value in fields.items():
            setattr(schedule, key, value)

        self.db.commit()
        self.db.refresh(schedule)
        return schedule

    def commit(self) -> None:
        self.db.commit()

    def refresh(self, schedule: IngestionSchedule) -> None:
        self.db.refresh(schedule)
