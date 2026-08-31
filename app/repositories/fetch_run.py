from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models.enums import FetchRunStatus, ProviderName
from app.models.fetch_run import FetchRun


class FetchRunRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create_pending(self, provider: ProviderName) -> FetchRun:
        fetch_run = FetchRun(
            provider=provider,
            status=FetchRunStatus.PENDING,
            started_at=datetime.now(UTC),
        )
        self.db.add(fetch_run)
        self.db.commit()
        self.db.refresh(fetch_run)
        return fetch_run

    def mark_success(self, fetch_run: FetchRun, *, records_fetched: int) -> FetchRun:
        fetch_run.status = FetchRunStatus.SUCCESS
        fetch_run.finished_at = datetime.now(UTC)
        fetch_run.records_fetched = records_fetched
        self.db.add(fetch_run)
        self.db.commit()
        self.db.refresh(fetch_run)
        return fetch_run

    def mark_failed(self, fetch_run: FetchRun, *, error_message: str) -> FetchRun:
        fetch_run.status = FetchRunStatus.FAILED
        fetch_run.finished_at = datetime.now(UTC)
        fetch_run.error_message = error_message
        self.db.add(fetch_run)
        self.db.commit()
        self.db.refresh(fetch_run)
        return fetch_run
