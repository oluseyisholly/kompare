from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.adapters.crypto.busha import BushaAdapter
from app.adapters.crypto.quidax import QuidaxAdapter
from app.core.config import ENABLE_INGESTION_SCHEDULER, INGESTION_SCHEDULER_POLL_SECONDS
from app.core.database import SessionLocal
from app.core.logger import logger
from app.models.enums import IngestionJobType
from app.repositories.asset import AssetRepository
from app.repositories.fetch_run import FetchRunRepository
from app.repositories.ingestion_schedule import IngestionScheduleRepository
from app.repositories.kyc import KycRepository
from app.repositories.provider import ProviderRepository
from app.repositories.provider_asset import ProviderAssetRepository
from app.repositories.quote import QuoteRepository
from app.repositories.raw_record import RawRecordRepository
from app.services.ingestion.busha import BushaIngestionService
from app.services.ingestion.focus import FocusAssetSelector
from app.services.ingestion.quidax import QuidaxIngestionService


class IngestionSchedulerService:
    """Simple in-process scheduler.

    This is not a queue worker. It polls due ingestion schedules and executes them
    inside the FastAPI process.
    """

    def __init__(
        self,
        *,
        enabled: bool = ENABLE_INGESTION_SCHEDULER,
        poll_seconds: int = INGESTION_SCHEDULER_POLL_SECONDS,
    ) -> None:
        self.enabled = enabled
        self.poll_seconds = max(5, poll_seconds)
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()
        self._running_keys: set[str] = set()

    async def start(self) -> None:
        if not self.enabled:
            logger.info("Ingestion scheduler is disabled")
            return
        if self._task is not None and not self._task.done():
            return

        logger.info("Starting ingestion scheduler with poll interval %s seconds", self.poll_seconds)
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run_loop(), name="ingestion-scheduler")

    async def stop(self) -> None:
        if self._task is None:
            return

        logger.info("Stopping ingestion scheduler")
        self._stop_event.set()
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        finally:
            self._task = None

    async def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                await self.run_pending_once()
            except Exception:
                logger.exception("Ingestion scheduler loop failed")

            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self.poll_seconds)
            except asyncio.TimeoutError:
                continue

    async def run_pending_once(self) -> None:
        db = SessionLocal()
        try:
            repository = IngestionScheduleRepository(db)
            now = datetime.now(UTC)
            schedules = repository.list_due(now)
            due_jobs = [(schedule.provider.slug, schedule.job_type) for schedule in schedules]
        finally:
            db.close()

        for provider_slug, job_type in due_jobs:
            running_key = f"{provider_slug}:{job_type.value}"
            if running_key in self._running_keys:
                continue

            self._running_keys.add(running_key)
            try:
                await self._run_job(provider_slug=provider_slug, job_type=job_type)
            finally:
                self._running_keys.discard(running_key)

    async def _run_job(self, *, provider_slug: str, job_type: IngestionJobType) -> None:
        db = SessionLocal()
        try:
            provider_repository = ProviderRepository(db)
            schedule_repository = IngestionScheduleRepository(db)

            provider = provider_repository.get_by_slug(provider_slug)
            if provider is None:
                logger.warning("Skipping scheduled job for missing provider=%s", provider_slug)
                return

            schedule = schedule_repository.get_by_provider_id_and_job_type(provider.id, job_type)
            if schedule is None or not schedule.is_enabled:
                return

            now = datetime.now(UTC)
            if schedule.next_run_at is None or schedule.next_run_at > now:
                return

            schedule.next_run_at = now + timedelta(minutes=schedule.interval_minutes)
            schedule_repository.commit()
            schedule_repository.refresh(schedule)

            logger.info(
                "Running scheduled ingestion for provider=%s job_type=%s",
                provider_slug,
                job_type.value,
            )

            await self._dispatch_job(db=db, provider_slug=provider_slug, job_type=job_type)

            schedule.last_run_at = datetime.now(UTC)
            schedule_repository.commit()
            schedule_repository.refresh(schedule)
        except Exception:
            db.rollback()
            logger.exception(
                "Scheduled ingestion failed for provider=%s job_type=%s",
                provider_slug,
                job_type.value,
            )
        finally:
            db.close()

    async def _dispatch_job(self, *, db: Session, provider_slug: str, job_type: IngestionJobType) -> None:
        if provider_slug == "quidax":
            service = QuidaxIngestionService(
                db=db,
                adapter=QuidaxAdapter(),
                fetch_run_repository=FetchRunRepository(db),
                raw_record_repository=RawRecordRepository(db),
                provider_asset_repository=ProviderAssetRepository(db),
                quote_repository=QuoteRepository(db),
                kyc_repository=KycRepository(db),
                focus_selector=FocusAssetSelector(),
            )
            await self._execute_job(service=service, job_type=job_type, provider_slug=provider_slug)
            return

        if provider_slug == "busha":
            service = BushaIngestionService(
                db=db,
                adapter=BushaAdapter(),
                asset_repository=AssetRepository(db),
                fetch_run_repository=FetchRunRepository(db),
                raw_record_repository=RawRecordRepository(db),
                provider_asset_repository=ProviderAssetRepository(db),
                quote_repository=QuoteRepository(db),
                kyc_repository=KycRepository(db),
                focus_selector=FocusAssetSelector(),
            )
            await self._execute_job(service=service, job_type=job_type, provider_slug=provider_slug)
            return

        logger.warning("No scheduler dispatcher configured for provider=%s", provider_slug)

    async def _execute_job(self, *, service: Any, job_type: IngestionJobType, provider_slug: str) -> None:
        if job_type == IngestionJobType.MARKET_DATA:
            await service.ingest_market_data()
            return
        if job_type == IngestionJobType.KYC:
            await service.ingest_kyc()
            return
        if job_type == IngestionJobType.FEES:
            logger.warning("Fees scheduler is not implemented yet for provider=%s", provider_slug)
            return

        logger.warning("Unsupported ingestion job type=%s for provider=%s", job_type.value, provider_slug)
