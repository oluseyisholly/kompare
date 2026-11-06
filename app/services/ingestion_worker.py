"""Durable at-least-once worker. Provider sessions stay outside API event loops."""

import asyncio
from datetime import UTC, datetime, timedelta

from app.core import config
from app.core.database import SessionLocal
from app.core.logger import logger
from app.models.enums import IngestionJobType
from app.repositories.ingestion_job import IngestionJobRepository
from app.services.ingestion_scheduler import IngestionSchedulerService


def execute_job(provider_slug, job_type, include_kyc):
    if job_type == "bootstrap":
        from app.services.ingestion.bootstrap import run_bootstrap_job

        return asyncio.run(run_bootstrap_job(provider_slug))
    from app.services.ingestion.manual import run_provider_ingestion_job

    return asyncio.run(
        run_provider_ingestion_job(
            provider_slug=provider_slug,
            job_type=IngestionJobType(job_type),
            include_kyc=include_kyc,
        )
    )


class IngestionWorker:
    def __init__(
        self,
        *,
        session_factory=SessionLocal,
        executor=execute_job,
        lease_seconds=None,
        max_attempts=None,
    ):
        self.sessions = session_factory
        self.executor = executor
        self.lease_seconds = max(3, lease_seconds or config.INGESTION_JOB_LEASE_SECONDS)
        self.max_attempts = max_attempts or config.INGESTION_JOB_MAX_ATTEMPTS

    async def run_once(self):
        with self.sessions() as db:
            row = IngestionJobRepository(db).claim(
                lease_seconds=self.lease_seconds,
                max_attempts=self.max_attempts,
            )
            if row is None:
                return False
            job_id, token, provider, kind, include_kyc = (
                row.id,
                row.lease_token,
                row.provider_slug,
                row.job_type,
                row.include_kyc,
            )
        done = asyncio.Event()

        async def renew():
            while not done.is_set():
                try:
                    await asyncio.wait_for(done.wait(), timeout=self.lease_seconds / 3)
                    return
                except asyncio.TimeoutError:
                    with self.sessions() as db:
                        if not IngestionJobRepository(db).heartbeat(
                            job_id,
                            token,
                            lease_seconds=self.lease_seconds,
                        ):
                            logger.error("Lost ingestion job lease id=%s", job_id)
                            return

        heartbeat = asyncio.create_task(renew())
        success = False
        try:
            result = await asyncio.to_thread(self.executor, provider, kind, include_kyc)
            success = not isinstance(result, dict) or result.get("status") not in {
                "failed",
                "partial",
                "skipped",
            }
        except Exception:
            logger.exception("Ingestion job failed id=%s", job_id)
        finally:
            done.set()
            try:
                await heartbeat
            except Exception:
                logger.exception("Ingestion job heartbeat failed id=%s", job_id)
            with self.sessions() as db:
                IngestionJobRepository(db).finish(job_id, token, success=success)
        return True


async def run_worker(*, stop, once=False):
    worker = IngestionWorker()
    scheduler = IngestionSchedulerService()
    next_cleanup = datetime.now(UTC)
    while not stop.is_set():
        if datetime.now(UTC) >= next_cleanup:
            from app.repositories.auth_rate_limit import AuthRateLimitRepository

            with worker.sessions() as db:
                AuthRateLimitRepository(db).prune_expired()
            next_cleanup = datetime.now(UTC) + timedelta(hours=6)
        if config.ENABLE_INGESTION_SCHEDULER:
            await scheduler.run_pending_once()
        worked = await worker.run_once()
        if once:
            return
        if not worked:
            try:
                await asyncio.wait_for(
                    stop.wait(), timeout=max(1, config.INGESTION_WORKER_POLL_SECONDS)
                )
            except asyncio.TimeoutError:
                pass
