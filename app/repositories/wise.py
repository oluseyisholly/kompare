"""Wise provider registration and compatibility facade over shared FX persistence."""

from app.models.enums import MarketCategory, ProviderName
from app.repositories.fx import FxRepository
from app.repositories.provider import ProviderRepository


class WiseRepository:
    def __init__(self, db):
        self.db = db
        self.fx = FxRepository(db)

    def register_provider(self):
        return ProviderRepository(self.db).get_or_create_by_slug(
            slug="wise",
            name="Wise",
            category=MarketCategory.FX,
            website_url="https://wise.com",
            has_adapter=True,
            metadata_json={"rate_classification": "reference_rate"},
        )

    def persist_rates(self, records, *, adapter, **context):
        return self.fx.persist_rates(
            records,
            provider=ProviderName.WISE,
            source_url=adapter.endpoint("rates"),
            api_version=adapter.api_version,
            **context,
        )

    def persist_currencies(self, records, **context):
        return self.fx.persist_currencies(records, **context)

    def save_quote(self, quote, **context):
        return self.fx.save_quote(quote, **context)

    def list_rates(self, **filters):
        return self.fx.list_rates(provider="wise", **filters)

    def list_currencies(self, *, page, per_page):
        provider = ProviderRepository(self.db).get_by_slug("wise")
        if provider is None:
            return [], 0
        return self.fx.list_currencies(
            provider_id=provider.id,
            page=page,
            per_page=per_page,
        )
