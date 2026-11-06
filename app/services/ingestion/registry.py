from __future__ import annotations

from sqlalchemy.orm import Session

from app.adapters.crypto.busha import BushaAdapter
from app.adapters.crypto.quidax import QuidaxAdapter
from app.adapters.giftcard.cardtonic import CardtonicAdapter
from app.adapters.giftcard.tbay import TbayAdapter
from app.models.enums import IngestionJobType
from app.repositories.asset import AssetRepository
from app.repositories.fetch_run import FetchRunRepository
from app.repositories.giftcard_rate import GiftCardRateRepository
from app.repositories.giftcard_variant import GiftCardVariantRepository
from app.repositories.kyc import KycRepository
from app.repositories.provider import ProviderRepository
from app.repositories.provider_asset import ProviderAssetRepository
from app.repositories.quote import QuoteRepository
from app.repositories.raw_record import RawRecordRepository
from app.repositories.tbay_catalog import TbayCatalogRepository
from app.services.ingestion.busha import BushaIngestionService
from app.services.ingestion.cardtonic import CardtonicIngestionService
from app.services.ingestion.focus import FocusAssetSelector
from app.services.ingestion.quidax import QuidaxIngestionService
from app.services.ingestion.tbay import TbayIngestionService


def _build_quidax_service(db: Session) -> QuidaxIngestionService:
    return QuidaxIngestionService(
        db=db,
        adapter=QuidaxAdapter(),
        fetch_run_repository=FetchRunRepository(db),
        raw_record_repository=RawRecordRepository(db),
        provider_asset_repository=ProviderAssetRepository(db),
        quote_repository=QuoteRepository(db),
        kyc_repository=KycRepository(db),
        focus_selector=FocusAssetSelector(),
    )


def _build_busha_service(db: Session) -> BushaIngestionService:
    return BushaIngestionService(
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


def _build_cardtonic_service(db: Session) -> CardtonicIngestionService:
    return CardtonicIngestionService(
        db=db,
        adapter=CardtonicAdapter(),
        asset_repository=AssetRepository(db),
        provider_repository=ProviderRepository(db),
        fetch_run_repository=FetchRunRepository(db),
        raw_record_repository=RawRecordRepository(db),
        giftcard_variant_repository=GiftCardVariantRepository(db),
        giftcard_rate_repository=GiftCardRateRepository(db),
        kyc_repository=KycRepository(db),
    )


def _build_tbay_service(db: Session) -> TbayIngestionService:
    return TbayIngestionService(
        adapter=TbayAdapter(),
        catalog_repository=TbayCatalogRepository(db, GiftCardRateRepository(db)),
        fetch_run_repository=FetchRunRepository(db),
    )


async def dispatch_ingestion(db, *, provider_slug, job_type, include_kyc=False):
    from app.services.ingestion.fx import FX_INGESTION_SERVICES, run_fx_ingestion

    if provider_slug in FX_INGESTION_SERVICES:
        return await run_fx_ingestion(
            db, provider=provider_slug, job_type=job_type, include_kyc=include_kyc
        )
    if provider_slug in {"stanbic", "united_capital"}:
        from app.services.ingestion.stanbic import StanbicIngestionService
        from app.services.ingestion.united_capital import UnitedCapitalIngestionService

        if include_kyc:
            raise ValueError("KYC is not implemented for mutual funds")
        service = (
            StanbicIngestionService if provider_slug == "stanbic" else UnitedCapitalIngestionService
        )(db)
    else:
        factory = {
            "quidax": _build_quidax_service,
            "busha": _build_busha_service,
            "cardtonic": _build_cardtonic_service,
            "tbay": _build_tbay_service,
        }.get(provider_slug)
        if factory is None:
            raise ValueError("No ingestion adapter configured for this provider")
        service = factory(db)
    if job_type == IngestionJobType.MARKET_DATA:
        if include_kyc:
            return await service.ingest(include_kyc=True)
        return await service.ingest_market_data()
    method = {
        IngestionJobType.KYC: "ingest_kyc",
        IngestionJobType.FUND_DETAILS: "ingest_fund_details",
    }.get(job_type)
    handler = getattr(service, method or "", None)
    if handler is None:
        raise ValueError("Ingestion job is not implemented for this provider")
    return await handler()
