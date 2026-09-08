from sqlalchemy.orm import Session, joinedload

from app.models.asset import Asset
from app.models.enums import ProviderName
from app.models.fetch_run import FetchRun
from app.models.giftcard_rate import GiftCardRate
from app.models.giftcard_variant import GiftCardVariant
from app.models.kyc import KycProfile
from app.models.provider import Provider
from app.models.provider_asset import ProviderAsset
from app.models.quote import Quote
from app.models.raw_record import RawRecord
from app.repositories.pagination import paginate_query


class ProviderRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_slug(self, slug: str) -> Provider | None:
        return self.db.query(Provider).filter(Provider.slug == slug).first()

    def list_all(self) -> list[Provider]:
        return self.db.query(Provider).order_by(Provider.name.asc(), Provider.id.asc()).all()

    def get_assets(self, provider: ProviderName, *, page: int, per_page: int) -> tuple[list[ProviderAsset], int]:
        query = (
            self.db.query(ProviderAsset)
            .options(joinedload(ProviderAsset.asset))
            .filter(ProviderAsset.provider == provider)
            .order_by(ProviderAsset.provider_symbol.asc())
        )
        return paginate_query(query, page=page, per_page=per_page)

    def get_quotes(self, provider: ProviderName, *, page: int, per_page: int) -> tuple[list[Quote], int]:
        query = (
            self.db.query(Quote)
            .options(joinedload(Quote.asset), joinedload(Quote.provider_asset))
            .filter(Quote.provider == provider)
            .order_by(Quote.captured_at.desc(), Quote.id.desc())
        )
        return paginate_query(query, page=page, per_page=per_page)

    def get_fetch_runs(self, provider: ProviderName, *, page: int, per_page: int) -> tuple[list[FetchRun], int]:
        query = (
            self.db.query(FetchRun)
            .filter(FetchRun.provider == provider)
            .order_by(FetchRun.started_at.desc(), FetchRun.id.desc())
        )
        return paginate_query(query, page=page, per_page=per_page)

    def get_raw_records(self, provider: ProviderName, *, page: int, per_page: int) -> tuple[list[RawRecord], int]:
        query = (
            self.db.query(RawRecord)
            .filter(RawRecord.provider == provider)
            .order_by(RawRecord.fetched_at.desc(), RawRecord.id.desc())
        )
        return paginate_query(query, page=page, per_page=per_page)

    def get_kyc_profiles(self, provider: ProviderName, *, page: int, per_page: int) -> tuple[list[KycProfile], int]:
        query = (
            self.db.query(KycProfile)
            .options(joinedload(KycProfile.levels))
            .filter(KycProfile.provider == provider)
            .order_by(KycProfile.fetched_at.desc(), KycProfile.id.desc())
        )
        return paginate_query(query, page=page, per_page=per_page)

    def get_giftcard_variants(
        self,
        provider_id: int,
        *,
        page: int,
        per_page: int,
        asset_code: str | None = None,
        source_currency: str | None = None,
        region: str | None = None,
        card_type: str | None = None,
    ) -> tuple[list[GiftCardVariant], int]:
        query = (
            self.db.query(GiftCardVariant)
            .options(joinedload(GiftCardVariant.asset), joinedload(GiftCardVariant.provider))
            .filter(GiftCardVariant.provider_id == provider_id)
            .order_by(GiftCardVariant.name.asc(), GiftCardVariant.id.asc())
        )

        if asset_code:
            query = query.join(GiftCardVariant.asset).filter(Asset.code == asset_code.upper())
        if source_currency:
            query = query.filter(GiftCardVariant.source_currency == source_currency.upper())
        if region:
            query = query.filter(GiftCardVariant.region == region)
        if card_type:
            query = query.filter(GiftCardVariant.card_type == card_type)

        return paginate_query(query, page=page, per_page=per_page)

    def get_giftcard_rates(
        self,
        provider_id: int,
        *,
        page: int,
        per_page: int,
        asset_code: str | None = None,
        source_currency: str | None = None,
        region: str | None = None,
        card_type: str | None = None,
    ) -> tuple[list[GiftCardRate], int]:
        query = (
            self.db.query(GiftCardRate)
            .options(
                joinedload(GiftCardRate.giftcard_variant).joinedload(GiftCardVariant.asset),
                joinedload(GiftCardRate.provider),
            )
            .join(GiftCardRate.giftcard_variant)
            .filter(GiftCardRate.provider_id == provider_id, GiftCardRate.superseded_at.is_(None))
            .order_by(GiftCardRate.captured_at.desc(), GiftCardRate.id.desc())
        )

        if asset_code:
            query = query.join(GiftCardVariant.asset).filter(Asset.code == asset_code.upper())
        if source_currency:
            query = query.filter(GiftCardRate.source_currency == source_currency.upper())
        if region:
            query = query.filter(GiftCardVariant.region == region)
        if card_type:
            query = query.filter(GiftCardVariant.card_type == card_type)

        return paginate_query(query, page=page, per_page=per_page)

    def create(self, provider: Provider) -> Provider:
        self.db.add(provider)
        self.db.commit()
        self.db.refresh(provider)
        return provider

    def update(self, provider: Provider, **fields) -> Provider:
        for key, value in fields.items():
            setattr(provider, key, value)

        self.db.commit()
        self.db.refresh(provider)
        return provider

    def get_or_create_by_slug(
        self,
        *,
        slug: str,
        name: str,
        category,
        description: str | None = None,
        logo_url: str | None = None,
        website_url: str | None = None,
        has_adapter: bool = False,
        metadata_json: dict | None = None,
    ) -> Provider:
        provider = self.get_by_slug(slug)
        if provider is not None:
            return provider

        provider = Provider(
            slug=slug,
            name=name,
            description=description,
            logo_url=logo_url,
            website_url=website_url,
            category=category,
            has_adapter=has_adapter,
            metadata_json=metadata_json,
        )
        return self.create(provider)
