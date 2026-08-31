from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.models.enums import ProviderName
from app.models.fetch_run import FetchRun
from app.models.kyc import KycProfile
from app.models.provider_asset import ProviderAsset
from app.models.quote import Quote
from app.models.raw_record import RawRecord
from app.repositories.pagination import paginate_query


class ReportRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_latest_fetch_run(self, provider: ProviderName) -> FetchRun | None:
        return (
            self.db.query(FetchRun)
            .filter(FetchRun.provider == provider)
            .order_by(FetchRun.started_at.desc(), FetchRun.id.desc())
            .first()
        )

    def count_assets(self, provider: ProviderName) -> int:
        return self.db.query(ProviderAsset).filter(ProviderAsset.provider == provider).count()

    def count_quotes(self, provider: ProviderName) -> int:
        return self.db.query(Quote).filter(Quote.provider == provider).count()

    def count_raw_records(self, provider: ProviderName) -> int:
        return self.db.query(RawRecord).filter(RawRecord.provider == provider).count()

    def count_kyc_profiles(self, provider: ProviderName) -> int:
        return self.db.query(KycProfile).filter(KycProfile.provider == provider).count()

    def get_latest_quote_at(self, provider: ProviderName):
        return self.db.query(func.max(Quote.captured_at)).filter(Quote.provider == provider).scalar()

    def get_latest_kyc_at(self, provider: ProviderName):
        return self.db.query(func.max(KycProfile.fetched_at)).filter(KycProfile.provider == provider).scalar()

    def get_latest_rates(self, provider: ProviderName, *, page: int, per_page: int) -> tuple[list[Quote], int]:
        query = (
            self.db.query(Quote)
            .options(joinedload(Quote.asset), joinedload(Quote.provider_asset))
            .filter(Quote.provider == provider)
            .order_by(Quote.captured_at.desc(), Quote.id.desc())
        )
        return paginate_query(query, page=page, per_page=per_page)

    def get_latest_quote_for_pair(
        self,
        provider: ProviderName,
        *,
        base_currency: str,
        quote_currency: str,
    ) -> Quote | None:
        return (
            self.db.query(Quote)
            .options(joinedload(Quote.asset), joinedload(Quote.provider_asset))
            .filter(
                Quote.provider == provider,
                Quote.base_currency == base_currency,
                Quote.quote_currency == quote_currency,
            )
            .order_by(Quote.captured_at.desc(), Quote.id.desc())
            .first()
        )

    def get_quote_trend(
        self,
        provider: ProviderName,
        *,
        base_currency: str,
        quote_currency: str,
        started_at: datetime,
        ended_at: datetime,
    ) -> list[Quote]:
        return (
            self.db.query(Quote)
            .options(joinedload(Quote.provider_asset))
            .filter(
                Quote.provider == provider,
                Quote.base_currency == base_currency,
                Quote.quote_currency == quote_currency,
                Quote.captured_at >= started_at,
                Quote.captured_at <= ended_at,
            )
            .order_by(Quote.captured_at.asc(), Quote.id.asc())
            .all()
        )

    def get_runs(self, provider: ProviderName) -> list[FetchRun]:
        return (
            self.db.query(FetchRun)
            .filter(FetchRun.provider == provider)
            .order_by(FetchRun.started_at.desc(), FetchRun.id.desc())
            .all()
        )

    def get_latest_kyc_profile(self, provider: ProviderName) -> KycProfile | None:
        return (
            self.db.query(KycProfile)
            .options(joinedload(KycProfile.levels))
            .filter(KycProfile.provider == provider)
            .order_by(KycProfile.fetched_at.desc(), KycProfile.id.desc())
            .first()
        )

    def get_raw_activity(self, provider: ProviderName) -> list[tuple]:
        return (
            self.db.query(RawRecord.source_type, func.count(RawRecord.id))
            .filter(RawRecord.provider == provider)
            .group_by(RawRecord.source_type)
            .all()
        )
