"""Small registry for provider-specific FX harvesting. Never used by conversion."""

from app.core.exceptions import AppError
from app.models.enums import IngestionJobType, MarketCategory
from app.repositories.provider import ProviderRepository
from app.schemas.common import ApiResponse
from app.schemas.fx import FxQuoteRead
from app.services.ingestion.fincra import FincraIngestionService
from app.services.ingestion.flutterwave import FlutterwaveIngestionService
from app.services.ingestion.wise import WiseIngestionService

FX_INGESTION_SERVICES = {
    "wise": WiseIngestionService,
    "flutterwave": FlutterwaveIngestionService,
    "fincra": FincraIngestionService,
}


def supported_fx_jobs(provider):
    factory = FX_INGESTION_SERVICES.get(provider)
    return {
        job
        for job, method in (
            (IngestionJobType.MARKET_DATA, "ingest_market_data"),
            (IngestionJobType.CURRENCIES, "ingest_currencies"),
        )
        if callable(getattr(factory, method, None))
    }


async def run_fx_ingestion(db, *, provider, job_type, include_kyc=False):
    factory = FX_INGESTION_SERVICES.get(provider)
    if factory is None or include_kyc or job_type not in supported_fx_jobs(provider):
        raise ValueError("FX ingestion provider or job is unsupported")
    service = factory(db)
    if job_type == IngestionJobType.MARKET_DATA:
        return await service.ingest_market_data()
    if job_type == IngestionJobType.CURRENCIES:
        return await service.ingest_currencies()
    raise ValueError("FX providers support market_data and currencies ingestion only")


class FxDiagnosticService:
    def __init__(self, db, *, handlers=None):
        self.db = db
        self.handlers = FX_INGESTION_SERVICES if handlers is None else handlers

    async def request_quote(self, provider, request):
        registered = ProviderRepository(self.db).get_by_slug(provider)
        if (
            registered is None
            or registered.category != MarketCategory.FX
            or not registered.is_active
        ):
            raise AppError(
                "FX provider is unavailable", status_code=404, error_code="fx_provider_unavailable"
            )
        factory = self.handlers.get(provider)
        if factory is None:
            raise AppError(
                "Quote harvesting is not implemented for this FX provider",
                status_code=503,
                error_code="fx_diagnostic_unavailable",
            )
        service = factory(self.db)
        harvest = getattr(service, "request_quote", None)
        if not callable(harvest):
            raise AppError(
                "Quote harvesting is not implemented for this FX provider",
                status_code=503,
                error_code="fx_diagnostic_unavailable",
            )
        quote = await harvest(request)
        quote = FxQuoteRead.model_validate(quote)
        if quote.provider != provider:
            raise AppError(
                "Diagnostic response provider did not match the request",
                status_code=502,
                error_code="fx_invalid_response",
            )
        return ApiResponse(
            responseCode=200,
            message="Amount-specific illustrative observation; not executable",
            data=quote,
        )
