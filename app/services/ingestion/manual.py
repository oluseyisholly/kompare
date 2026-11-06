"""Manual requests are persisted before acknowledgement; workers execute them."""

from app.core.database import SessionLocal
from app.repositories.ingestion_job import IngestionJobRepository
from app.repositories.provider import ProviderRepository
from app.repositories.provider_metric import ProviderMetricRepository
from app.services.ingestion.registry import dispatch_ingestion
from app.services.provider_metric import ProviderMetricService


async def run_provider_ingestion_job(*, provider_slug, job_type, include_kyc=False):
    # Own the session in the worker thread, never reuse an HTTP request session.
    with SessionLocal() as db:
        result = await dispatch_ingestion(
            db, provider_slug=provider_slug, job_type=job_type, include_kyc=include_kyc
        )
        ProviderMetricService(
            repository=ProviderMetricRepository(db), provider_repository=ProviderRepository(db)
        ).refresh_provider_by_slug(provider_slug)
        return result


def launch_provider_ingestion_job(*, provider_slug, job_type, include_kyc=False, db=None):
    if db is None:
        with SessionLocal() as session:
            return launch_provider_ingestion_job(
                provider_slug=provider_slug, job_type=job_type, include_kyc=include_kyc, db=session
            )
    return IngestionJobRepository(db).enqueue(
        provider_slug=provider_slug, job_type=job_type.value, include_kyc=include_kyc
    )
