from sqlalchemy.orm import Session, joinedload

from app.models.enums import ProviderName
from app.models.fetch_run import FetchRun
from app.models.kyc import KycProfile
from app.models.provider_asset import ProviderAsset
from app.models.quote import Quote
from app.models.raw_record import RawRecord


class PlatformRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_platforms(self) -> list[str]:
        return [provider.value for provider in ProviderName]

    def get_assets(self, provider: ProviderName, *, page: int, per_page: int) -> tuple[list[ProviderAsset], int]:
        query = (
            self.db.query(ProviderAsset)
            .options(joinedload(ProviderAsset.asset))
            .filter(ProviderAsset.provider == provider)
            .order_by(ProviderAsset.provider_symbol.asc())
        )
        total = query.count()
        rows = query.offset((page - 1) * per_page).limit(per_page).all()
        return rows, total

    def get_quotes(self, provider: ProviderName, *, page: int, per_page: int) -> tuple[list[Quote], int]:
        query = (
            self.db.query(Quote)
            .options(joinedload(Quote.asset), joinedload(Quote.provider_asset))
            .filter(Quote.provider == provider)
            .order_by(Quote.captured_at.desc(), Quote.id.desc())
        )
        total = query.count()
        rows = query.offset((page - 1) * per_page).limit(per_page).all()
        return rows, total

    def get_fetch_runs(self, provider: ProviderName, *, page: int, per_page: int) -> tuple[list[FetchRun], int]:
        query = (
            self.db.query(FetchRun)
            .filter(FetchRun.provider == provider)
            .order_by(FetchRun.started_at.desc(), FetchRun.id.desc())
        )
        total = query.count()
        rows = query.offset((page - 1) * per_page).limit(per_page).all()
        return rows, total

    def get_raw_records(self, provider: ProviderName, *, page: int, per_page: int) -> tuple[list[RawRecord], int]:
        query = (
            self.db.query(RawRecord)
            .filter(RawRecord.provider == provider)
            .order_by(RawRecord.fetched_at.desc(), RawRecord.id.desc())
        )
        total = query.count()
        rows = query.offset((page - 1) * per_page).limit(per_page).all()
        return rows, total

    def get_kyc_profiles(self, provider: ProviderName, *, page: int, per_page: int) -> tuple[list[KycProfile], int]:
        query = (
            self.db.query(KycProfile)
            .options(joinedload(KycProfile.levels))
            .filter(KycProfile.provider == provider)
            .order_by(KycProfile.fetched_at.desc(), KycProfile.id.desc())
        )
        total = query.count()
        rows = query.offset((page - 1) * per_page).limit(per_page).all()
        return rows, total
