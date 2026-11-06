from fastapi import Depends
from sqlalchemy.orm import Session

from app.adapters.crypto.busha import BushaAdapter
from app.adapters.crypto.quidax import QuidaxAdapter
from app.adapters.giftcard.cardtonic import CardtonicAdapter
from app.adapters.giftcard.tbay import TbayAdapter
from app.core.database import get_db
from app.repositories.asset import AssetRepository
from app.repositories.audit_log import AuditLogRepository
from app.repositories.email_verification_otp import EmailVerificationOtpRepository
from app.repositories.fetch_run import FetchRunRepository
from app.repositories.giftcard_rate import GiftCardRateRepository
from app.repositories.giftcard_variant import GiftCardVariantRepository
from app.repositories.ingestion_schedule import IngestionScheduleRepository
from app.repositories.kyc import KycRepository
from app.repositories.provider import ProviderRepository
from app.repositories.provider_asset import ProviderAssetRepository
from app.repositories.provider_metric import ProviderMetricRepository
from app.repositories.provider_review import ProviderReviewRepository
from app.repositories.quote import QuoteRepository
from app.repositories.raw_record import RawRecordRepository
from app.repositories.refresh_token import RefreshTokenRepository
from app.repositories.report import ReportRepository
from app.repositories.tbay_catalog import TbayCatalogRepository
from app.repositories.user import UserRepository
from app.repositories.user_deletion_request import UserDeletionRequestRepository
from app.repositories.verification_otp import VerificationOtpRepository
from app.services.admin_user import AdminUserService
from app.services.audit_log import AuditLogService
from app.services.auth import AuthService
from app.services.busha import BushaService
from app.services.email import EmailService
from app.services.ingestion.busha import BushaIngestionService
from app.services.ingestion.cardtonic import CardtonicIngestionService
from app.services.ingestion.focus import FocusAssetSelector
from app.services.ingestion.quidax import QuidaxIngestionService
from app.services.ingestion.tbay import TbayIngestionService
from app.services.provider import ProviderService
from app.services.provider_metric import ProviderMetricService
from app.services.provider_review import ProviderReviewService
from app.services.quidax import QuidaxService
from app.services.report import ReportService


def get_quidax_adapter() -> QuidaxAdapter:
    return QuidaxAdapter()


def get_busha_adapter() -> BushaAdapter:
    return BushaAdapter()


def get_cardtonic_adapter() -> CardtonicAdapter:
    return CardtonicAdapter()


def build_tbay_ingestion_service(db: Session) -> TbayIngestionService:
    return TbayIngestionService(
        adapter=TbayAdapter(),
        catalog_repository=TbayCatalogRepository(db, GiftCardRateRepository(db)),
        fetch_run_repository=FetchRunRepository(db),
    )


def get_tbay_ingestion_service(db: Session = Depends(get_db)) -> TbayIngestionService:
    return build_tbay_ingestion_service(db)


def get_focus_asset_selector() -> FocusAssetSelector:
    return FocusAssetSelector()


def get_asset_repository(db: Session = Depends(get_db)) -> AssetRepository:
    return AssetRepository(db)


def get_provider_repository(db: Session = Depends(get_db)) -> ProviderRepository:
    return ProviderRepository(db)


def get_provider_metric_repository(db: Session = Depends(get_db)) -> ProviderMetricRepository:
    return ProviderMetricRepository(db)


def get_audit_log_repository(db: Session = Depends(get_db)) -> AuditLogRepository:
    return AuditLogRepository(db)


def get_audit_log_service(
    repository: AuditLogRepository = Depends(get_audit_log_repository),
) -> AuditLogService:
    return AuditLogService(repository=repository)


def get_email_service() -> EmailService:
    return EmailService()


def get_ingestion_schedule_repository(db: Session = Depends(get_db)) -> IngestionScheduleRepository:
    return IngestionScheduleRepository(db)


def get_user_repository(db: Session = Depends(get_db)) -> UserRepository:
    return UserRepository(db)


def get_user_deletion_request_repository(
    db: Session = Depends(get_db),
) -> UserDeletionRequestRepository:
    return UserDeletionRequestRepository(db)


def get_email_verification_otp_repository(
    db: Session = Depends(get_db),
) -> EmailVerificationOtpRepository:
    return EmailVerificationOtpRepository(db)


def get_verification_otp_repository(db: Session = Depends(get_db)) -> VerificationOtpRepository:
    return VerificationOtpRepository(db)


def get_refresh_token_repository(db: Session = Depends(get_db)) -> RefreshTokenRepository:
    return RefreshTokenRepository(db)


def get_report_repository(db: Session = Depends(get_db)) -> ReportRepository:
    return ReportRepository(db)


def get_fetch_run_repository(db: Session = Depends(get_db)) -> FetchRunRepository:
    return FetchRunRepository(db)


def get_giftcard_variant_repository(db: Session = Depends(get_db)) -> GiftCardVariantRepository:
    return GiftCardVariantRepository(db)


def get_giftcard_rate_repository(db: Session = Depends(get_db)) -> GiftCardRateRepository:
    return GiftCardRateRepository(db)


def get_raw_record_repository(db: Session = Depends(get_db)) -> RawRecordRepository:
    return RawRecordRepository(db)


def get_provider_asset_repository(db: Session = Depends(get_db)) -> ProviderAssetRepository:
    return ProviderAssetRepository(db)


def get_provider_review_repository(db: Session = Depends(get_db)) -> ProviderReviewRepository:
    return ProviderReviewRepository(db)


def get_quote_repository(db: Session = Depends(get_db)) -> QuoteRepository:
    return QuoteRepository(db)


def get_kyc_repository(db: Session = Depends(get_db)) -> KycRepository:
    return KycRepository(db)


def get_provider_metric_service(
    repository: ProviderMetricRepository = Depends(get_provider_metric_repository),
    provider_repository: ProviderRepository = Depends(get_provider_repository),
) -> ProviderMetricService:
    return ProviderMetricService(repository=repository, provider_repository=provider_repository)


def get_provider_service(
    repository: ProviderRepository = Depends(get_provider_repository),
    ingestion_schedule_repository: IngestionScheduleRepository = Depends(
        get_ingestion_schedule_repository
    ),
    kyc_repository: KycRepository = Depends(get_kyc_repository),
    giftcard_variant_repository: GiftCardVariantRepository = Depends(
        get_giftcard_variant_repository
    ),
    giftcard_rate_repository: GiftCardRateRepository = Depends(get_giftcard_rate_repository),
    provider_metric_service: ProviderMetricService = Depends(get_provider_metric_service),
) -> ProviderService:
    return ProviderService(
        repository=repository,
        ingestion_schedule_repository=ingestion_schedule_repository,
        kyc_repository=kyc_repository,
        giftcard_variant_repository=giftcard_variant_repository,
        giftcard_rate_repository=giftcard_rate_repository,
        provider_metric_service=provider_metric_service,
    )


def get_provider_review_service(
    repository: ProviderReviewRepository = Depends(get_provider_review_repository),
    provider_repository: ProviderRepository = Depends(get_provider_repository),
    audit_log_service: AuditLogService = Depends(get_audit_log_service),
    provider_metric_service: ProviderMetricService = Depends(get_provider_metric_service),
) -> ProviderReviewService:
    return ProviderReviewService(
        repository=repository,
        provider_repository=provider_repository,
        audit_log_service=audit_log_service,
        provider_metric_service=provider_metric_service,
    )


def get_auth_service(
    repository: UserRepository = Depends(get_user_repository),
    refresh_token_repository: RefreshTokenRepository = Depends(get_refresh_token_repository),
    verification_otp_repository: VerificationOtpRepository = Depends(
        get_verification_otp_repository
    ),
    email_service: EmailService = Depends(get_email_service),
) -> AuthService:
    return AuthService(
        repository=repository,
        refresh_token_repository=refresh_token_repository,
        verification_otp_repository=verification_otp_repository,
        email_service=email_service,
    )


def get_admin_user_service(
    user_repository: UserRepository = Depends(get_user_repository),
    deletion_request_repository: UserDeletionRequestRepository = Depends(
        get_user_deletion_request_repository
    ),
    auth_service: AuthService = Depends(get_auth_service),
    audit_log_service: AuditLogService = Depends(get_audit_log_service),
    provider_review_service: ProviderReviewService = Depends(get_provider_review_service),
) -> AdminUserService:
    return AdminUserService(
        user_repository=user_repository,
        deletion_request_repository=deletion_request_repository,
        auth_service=auth_service,
        audit_log_service=audit_log_service,
        provider_review_service=provider_review_service,
    )


def get_report_service(
    repository: ReportRepository = Depends(get_report_repository),
    provider_repository: ProviderRepository = Depends(get_provider_repository),
) -> ReportService:
    return ReportService(repository=repository, provider_repository=provider_repository)


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


def get_cardtonic_ingestion_service(
    db: Session = Depends(get_db),
    adapter: CardtonicAdapter = Depends(get_cardtonic_adapter),
    asset_repository: AssetRepository = Depends(get_asset_repository),
    provider_repository: ProviderRepository = Depends(get_provider_repository),
    fetch_run_repository: FetchRunRepository = Depends(get_fetch_run_repository),
    raw_record_repository: RawRecordRepository = Depends(get_raw_record_repository),
    giftcard_variant_repository: GiftCardVariantRepository = Depends(
        get_giftcard_variant_repository
    ),
    giftcard_rate_repository: GiftCardRateRepository = Depends(get_giftcard_rate_repository),
    kyc_repository: KycRepository = Depends(get_kyc_repository),
) -> CardtonicIngestionService:
    return CardtonicIngestionService(
        db=db,
        adapter=adapter,
        asset_repository=asset_repository,
        provider_repository=provider_repository,
        fetch_run_repository=fetch_run_repository,
        raw_record_repository=raw_record_repository,
        giftcard_variant_repository=giftcard_variant_repository,
        giftcard_rate_repository=giftcard_rate_repository,
        kyc_repository=kyc_repository,
    )
