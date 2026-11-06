from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from app.core.config import ENABLE_INGESTION_SCHEDULER, INGESTION_SCHEDULER_POLL_SECONDS
from app.core.database import SessionLocal
from app.core.logger import logger
from app.repositories.ingestion_schedule import IngestionScheduleRepository
from app.repositories.provider import ProviderRepository


class IngestionSchedulerService:
    """Poll schedules and atomically enqueue durable jobs; never fetch provider data here."""

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

    async def run_pending_once(self):
        await asyncio.to_thread(self._enqueue_due)

    def _enqueue_due(self):
        with SessionLocal() as db:
            repository = IngestionScheduleRepository(db)
            now = datetime.now(UTC)
            schedules = repository.list_due(now)
            for schedule in schedules:
                repository.enqueue_due(schedule.id, now=now)

    async def _run_job(self, *, provider_slug, job_type):
        with SessionLocal() as db:
            provider = ProviderRepository(db).get_by_slug(provider_slug)
            if provider is not None:
                schedule = IngestionScheduleRepository(db).get_by_provider_id_and_job_type(
                    provider.id, job_type
                )
                if schedule is not None:
                    IngestionScheduleRepository(db).enqueue_due(schedule.id, now=datetime.now(UTC))

    async def _dispatch_job(self, *, db, provider_slug, job_type):
        # Retained for direct dispatch/testing; scheduled jobs are now durable requests.
        from app.services.ingestion.registry import dispatch_ingestion

        return await dispatch_ingestion(db, provider_slug=provider_slug, job_type=job_type)
