import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, or_

from app.models.ingestion_job import IngestionJob


class IngestionJobRepository:
    def __init__(self, db):
        self.db = db

    def enqueue(self, *, provider_slug, job_type, include_kyc=False, commit=True):
        row = IngestionJob(
            provider_slug=provider_slug,
            job_type=job_type,
            include_kyc=include_kyc,
            status="pending",
            attempts=0,
        )
        self.db.add(row)
        self.db.flush()
        job_id = row.id
        if commit:
            self.db.commit()
        return job_id

    def claim(self, *, lease_seconds, max_attempts, now=None):
        now = now or datetime.now(UTC)
        try:
            self.db.query(IngestionJob).filter(
                IngestionJob.status == "running",
                IngestionJob.leased_until <= now,
                IngestionJob.attempts >= max_attempts,
            ).update(
                {
                    "status": "failed",
                    "finished_at": now,
                    "error_message": "Worker lease expired; retry limit reached",
                },
                synchronize_session=False,
            )
            row = (
                self.db.query(IngestionJob)
                .filter(
                    or_(
                        IngestionJob.status == "pending",
                        and_(
                            IngestionJob.status == "running",
                            IngestionJob.leased_until <= now,
                        ),
                    ),
                    IngestionJob.attempts < max_attempts,
                )
                .order_by(IngestionJob.id)
                .with_for_update(skip_locked=True)
                .populate_existing()
                .first()
            )
            if row is None:
                self.db.commit()
                return None
            row.status = "running"
            row.attempts += 1
            row.lease_token = secrets.token_urlsafe(32)
            row.leased_until = now + timedelta(seconds=lease_seconds)
            self.db.commit()
            self.db.refresh(row)
            return row
        except Exception:
            self.db.rollback()
            raise

    def heartbeat(self, job_id, token, *, lease_seconds, now=None):
        now = now or datetime.now(UTC)
        changed = (
            self.db.query(IngestionJob)
            .filter(
                IngestionJob.id == job_id,
                IngestionJob.status == "running",
                IngestionJob.lease_token == token,
                IngestionJob.leased_until > now,
            )
            .update(
                {"leased_until": now + timedelta(seconds=lease_seconds)}, synchronize_session=False
            )
        )
        self.db.commit()
        return changed == 1

    def finish(self, job_id, token, *, success, now=None):
        now = now or datetime.now(UTC)
        changed = (
            self.db.query(IngestionJob)
            .filter(
                IngestionJob.id == job_id,
                IngestionJob.status == "running",
                IngestionJob.lease_token == token,
                IngestionJob.leased_until > now,
            )
            .update(
                {
                    "status": "success" if success else "failed",
                    "finished_at": now,
                    "leased_until": None,
                    "lease_token": None,
                    "error_message": None
                    if success
                    else "Ingestion failed; inspect provider fetch runs",
                },
                synchronize_session=False,
            )
        )
        if changed and success:
            from app.models.enums import IngestionJobType
            from app.models.ingestion_schedule import IngestionSchedule
            from app.models.provider import Provider

            row = self.db.get(IngestionJob, job_id)
            if row.job_type != "bootstrap":
                provider_id = self.db.query(Provider.id).filter_by(slug=row.provider_slug).scalar()
                if provider_id is not None:
                    self.db.query(IngestionSchedule).filter_by(
                        provider_id=provider_id, job_type=IngestionJobType(row.job_type)
                    ).update({"last_run_at": now}, synchronize_session=False)
        self.db.commit()
        return changed == 1
