from fastapi import Depends
from sqlalchemy.orm import Session

from app.adapters.crypto.busha import BushaAdapter
from app.adapters.crypto.quidax import QuidaxAdapter
from app.core.database import get_db
from app.repositories.asset import AssetRepository
from app.repositories.fetch_run import FetchRunRepository
from app.repositories.kyc import KycRepository
from app.repositories.platform import PlatformRepository
from app.repositories.provider import ProviderRepository
from app.repositories.provider_asset import ProviderAssetRepository
from app.repositories.quote import QuoteRepository
from app.repositories.raw_record import RawRecordRepository
from app.repositories.report import ReportRepository
from app.services.busha import BushaService
from app.services.ingestion.busha import BushaIngestionService
from app.services.ingestion.focus import FocusAssetSelector
from app.services.ingestion.quidax import QuidaxIngestionService
from app.services.platform import PlatformService
from app.services.provider import ProviderService
from app.services.quidax import QuidaxService
from app.services.report import ReportService


def get_quidax_adapter() -> QuidaxAdapter:
    return QuidaxAdapter()


def get_busha_adapter() -> BushaAdapter:
    return BushaAdapter()


def get_focus_asset_selector() -> FocusAssetSelector:
    return FocusAssetSelector()


def get_asset_repository(db: Session = Depends(get_db)) -> AssetRepository:
    return AssetRepository(db)


def get_platform_repository(db: Session = Depends(get_db)) -> PlatformRepository:
    return PlatformRepository(db)


def get_provider_repository(db: Session = Depends(get_db)) -> ProviderRepository:
    return ProviderRepository(db)


def get_report_repository(db: Session = Depends(get_db)) -> ReportRepository:
    return ReportRepository(db)


def get_fetch_run_repository(db: Session = Depends(get_db)) -> FetchRunRepository:
    return FetchRunRepository(db)


def get_raw_record_repository(db: Session = Depends(get_db)) -> RawRecordRepository:
    return RawRecordRepository(db)


def get_provider_asset_repository(db: Session = Depends(get_db)) -> ProviderAssetRepository:
    return ProviderAssetRepository(db)


def get_quote_repository(db: Session = Depends(get_db)) -> QuoteRepository:
    return QuoteRepository(db)


def get_kyc_repository(db: Session = Depends(get_db)) -> KycRepository:
    return KycRepository(db)


def get_platform_service(
    repository: PlatformRepository = Depends(get_platform_repository),
    kyc_repository: KycRepository = Depends(get_kyc_repository),
) -> PlatformService:
    return PlatformService(repository=repository, kyc_repository=kyc_repository)


def get_provider_service(
    repository: ProviderRepository = Depends(get_provider_repository),
) -> ProviderService:
    return ProviderService(repository=repository)


def get_report_service(
    repository: ReportRepository = Depends(get_report_repository),
) -> ReportService:
    return ReportService(repository=repository)


def get_quidax_service(
    adapter: QuidaxAdapter = Depends(get_quidax_adapter),
) -> QuidaxService:
    return QuidaxService(adapter=adapter)


def get_busha_service(
    adapter: BushaAdapter = Depends(get_busha_adapter),
    focus_selector: FocusAssetSelector = Depends(get_focus_asset_selector),
) -> BushaService:
    return BushaService(adapter=adapter, focus_selector=focus_selector)


def get_quidax_ingestion_service(
    db: Session = Depends(get_db),
    adapter: QuidaxAdapter = Depends(get_quidax_adapter),
    fetch_run_repository: FetchRunRepository = Depends(get_fetch_run_repository),
    raw_record_repository: RawRecordRepository = Depends(get_raw_record_repository),
    provider_asset_repository: ProviderAssetRepository = Depends(get_provider_asset_repository),
    quote_repository: QuoteRepository = Depends(get_quote_repository),
    kyc_repository: KycRepository = Depends(get_kyc_repository),
    focus_selector: FocusAssetSelector = Depends(get_focus_asset_selector),
) -> QuidaxIngestionService:
    return QuidaxIngestionService(
        db=db,
        adapter=adapter,
        fetch_run_repository=fetch_run_repository,
        raw_record_repository=raw_record_repository,
        provider_asset_repository=provider_asset_repository,
        quote_repository=quote_repository,
        kyc_repository=kyc_repository,
        focus_selector=focus_selector,
    )


def get_busha_ingestion_service(
    db: Session = Depends(get_db),
    adapter: BushaAdapter = Depends(get_busha_adapter),
    asset_repository: AssetRepository = Depends(get_asset_repository),
    fetch_run_repository: FetchRunRepository = Depends(get_fetch_run_repository),
    raw_record_repository: RawRecordRepository = Depends(get_raw_record_repository),
    provider_asset_repository: ProviderAssetRepository = Depends(get_provider_asset_repository),
    quote_repository: QuoteRepository = Depends(get_quote_repository),
    kyc_repository: KycRepository = Depends(get_kyc_repository),
    focus_selector: FocusAssetSelector = Depends(get_focus_asset_selector),
) -> BushaIngestionService:
    return BushaIngestionService(
        db=db,
        adapter=adapter,
        asset_repository=asset_repository,
        fetch_run_repository=fetch_run_repository,
        raw_record_repository=raw_record_repository,
        provider_asset_repository=provider_asset_repository,
        quote_repository=quote_repository,
        kyc_repository=kyc_repository,
        focus_selector=focus_selector,
    )
