from datetime import datetime

from sqlalchemy import func

from app.models.asset import Asset
from app.models.enums import MarketCategory, ProviderName, QuoteType
from app.models.fx import FxCurrency, FxQuoteObservation
from app.models.provider import Provider
from app.models.quote import Quote
from app.repositories.asset import AssetRepository
from app.repositories.pagination import paginate_query
from app.repositories.quote import QuoteRepository
from app.schemas.fx import FxCurrencyRecord, FxReferenceRate
from app.utils.currency_precision import currency_precision


class FxRepository:
    def __init__(self, db):
        self.db = db

    def get_rate(self, *, provider, source, target):
        try:
            provider_name = ProviderName(provider)
        except ValueError:
            return None
        return (
            self.db.query(Quote)
            .filter(
                Quote.provider == provider_name,
                Quote.base_currency == source,
                Quote.quote_currency == target,
                Quote.superseded_at.is_(None),
                Quote.metadata_json["classification"].as_string() == "reference_rate",
            )
            .order_by(Quote.captured_at.desc(), Quote.id.desc())
            .first()
        )

    def get_currency(self, *, provider_id, code):
        return (
            self.db.query(FxCurrency)
            .filter_by(
                provider_id=provider_id,
                code=code,
                is_active=True,
            )
            .one_or_none()
        )

    def list_rates(self, *, provider, source, target, page, per_page):
        try:
            provider_name = ProviderName(provider)
        except ValueError:
            return [], 0
        query = self.db.query(Quote).filter(
            Quote.provider == provider_name,
            Quote.superseded_at.is_(None),
            Quote.metadata_json["classification"].as_string() == "reference_rate",
        )
        if source:
            query = query.filter(Quote.base_currency == source)
        if target:
            query = query.filter(Quote.quote_currency == target)
        return paginate_query(
            query.order_by(Quote.base_currency, Quote.quote_currency),
            page=page,
            per_page=per_page,
        )

    def list_currencies(self, *, provider_id, page, per_page):
        query = self.db.query(FxCurrency).filter_by(
            provider_id=provider_id,
            is_active=True,
        )
        return paginate_query(query.order_by(FxCurrency.code), page=page, per_page=per_page)

    def persist_rates(
        self,
        records,
        *,
        provider,
        source_url,
        api_version,
        fetch_run_id,
        raw_record_id,
        captured_at,
    ):
        provider = ProviderName(provider)
        records = [FxReferenceRate.model_validate(record) for record in records]
        codes = {r.source_currency for r in records}
        assets = AssetRepository(self.db).get_by_codes(codes)
        for code in sorted(codes - assets.keys()):
            assets[code] = Asset(code=code, name=code, category=MarketCategory.FX, is_active=True)
            self.db.add(assets[code])
        self.db.flush()
        # Use the same stable parent locks and ordering as create_many, before
        # reading timestamps. Keep them through the check and write transaction.
        # A waiting ingestion must see the rate committed by the previous writer.
        self.db.query(Asset).filter(Asset.id.in_({asset.id for asset in assets.values()})).order_by(
            Asset.id
        ).with_for_update().all()
        current = {
            (q.base_currency, q.quote_currency): q
            for q in self.db.query(Quote)
            .filter(
                Quote.provider == provider,
                Quote.superseded_at.is_(None),
            )
            .populate_existing()
            .all()
        }
        quotes, failures = [], []
        for record in records:
            asset = assets[record.source_currency]
            if asset.category != MarketCategory.FX:
                failures.append(
                    {"source": record.source_currency, "error": "Asset category conflict"}
                )
                continue
            prior = current.get((record.source_currency, record.target_currency))
            prior_time = (prior.metadata_json or {}).get("provider_time") if prior else None
            if prior_time and datetime.fromisoformat(prior_time) > record.provider_time:
                failures.append(
                    {
                        "source": record.source_currency,
                        "target": record.target_currency,
                        "error": "Provider timestamp regressed; current rate preserved",
                    }
                )
                continue
            quotes.append(
                Quote(
                    provider=provider,
                    asset_id=asset.id,
                    quote_type=QuoteType.MARKET,
                    base_currency=record.source_currency,
                    quote_currency=record.target_currency,
                    mid_rate=record.rate,
                    fetch_run_id=fetch_run_id,
                    raw_record_id=raw_record_id,
                    captured_at=captured_at,
                    metadata_json={
                        "classification": "reference_rate",
                        "transfer_route_verified": False,
                        "provider_time": record.provider_time.isoformat(),
                        # Keep full provider precision alongside the legacy Numeric(24,8) column.
                        "provider_rate": str(record.rate),
                        "source_url": source_url,
                        "api_version": api_version,
                    },
                )
            )
        created = QuoteRepository(self.db).create_many(quotes)
        return {
            "rates_observed": len(quotes),
            "versions_created": created,
            "persistence_failures": failures,
        }

    def persist_currencies(
        self,
        records,
        *,
        provider_id,
        source_url,
        captured_at,
        fetch_run_id,
        raw_record_id,
        snapshot_complete: bool,
    ):
        """Atomically apply a scoped snapshot; only explicit complete snapshots retire rows.

        Fetch-run IDs are allocated before fetching. A provider-row lock serializes
        writers even when no currency rows exist. The largest committed currency
        fetch-run ID is the durable, provider-wide refresh watermark.
        """
        try:
            if not isinstance(snapshot_complete, bool):
                raise ValueError("Currency snapshot completeness must be an explicit boolean")
            records = [FxCurrencyRecord.model_validate(record) for record in records]
            if not records:
                raise ValueError("Empty currency snapshots cannot retire currencies")
            codes = {record.code for record in records}
            if len(codes) != len(records):
                raise ValueError("Duplicate currency codes in persistence snapshot")
            # Lock a stable parent, not just existing currencies: first refreshes
            # and concurrent inserts must serialize too. No network work occurs here.
            self.db.query(Provider.id).filter(Provider.id == provider_id).with_for_update().one()
            scope = self.db.query(FxCurrency).filter_by(
                provider_id=provider_id,
            )
            latest_run_id = scope.with_entities(func.max(FxCurrency.fetch_run_id)).scalar()
            if latest_run_id is not None and fetch_run_id < latest_run_id:
                self.db.commit()
                return {
                    "currencies_observed": 0,
                    "currencies_deactivated": 0,
                    "snapshot_complete": snapshot_complete,
                    "superseded": True,
                    "latest_currency_fetch_run_id": latest_run_id,
                }
            # Refresh already-loaded objects after waiting for another writer's lock.
            current = {
                row.code: row
                for row in scope.order_by(
                    FxCurrency.fetch_run_id, FxCurrency.captured_at, FxCurrency.id
                )
                .populate_existing()
                .all()
            }
            for record in records:
                row = current.get(record.code)
                if row is None:
                    row = FxCurrency(provider_id=provider_id, code=record.code)
                    self.db.add(row)
                row.is_active = True
                if record.name is not None:
                    row.name = record.name
                if record.symbol is not None:
                    row.symbol = record.symbol
                if record.supports_decimals is not None:
                    row.supports_decimals = record.supports_decimals
                row.decimal_places, row.precision_source = currency_precision(
                    record.code,
                    supports_decimals=row.supports_decimals,
                    provider_source=source_url,
                )
                row.country_keywords = record.country_keywords
                row.captured_at = captured_at
                row.source_url = source_url
                row.fetch_run_id = fetch_run_id
                row.raw_record_id = raw_record_id
            deactivated = 0
            if snapshot_complete:
                for code, row in current.items():
                    if code not in codes and row.is_active:
                        row.is_active = False
                        # Retain the last observation's raw/run/capture provenance.
                        deactivated += 1
            self.db.commit()
            return {
                "currencies_observed": len(records),
                "currencies_deactivated": deactivated,
                "snapshot_complete": snapshot_complete,
                "superseded": False,
                "latest_currency_fetch_run_id": fetch_run_id,
            }
        except Exception:
            self.db.rollback()
            raise

    def save_quote(self, quote, *, provider_id, raw_record_id, fetch_run_id):
        from app.repositories.provider import ProviderRepository

        provider = ProviderRepository(self.db).get_by_slug(quote.provider)
        if provider is None or provider.id != provider_id:
            raise ValueError("Quote provider does not match the registered observation provider")
        row = FxQuoteObservation(
            provider_id=provider_id,
            source_currency=quote.source_currency,
            target_currency=quote.target_currency,
            requested_amount=quote.requested_amount,
            amount_basis=quote.amount_basis,
            captured_at=quote.captured_at,
            expires_at=quote.expires_at,
            fetch_run_id=fetch_run_id,
            raw_record_id=raw_record_id,
            response_data=quote.model_dump(mode="json"),
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def save_transfer_rate(self, record, *, provider_id, fetch_run_id, raw_record_id):
        from app.repositories.provider import ProviderRepository
        from app.schemas.fx import FxTransferRateRead

        record = FxTransferRateRead.model_validate(record)
        registered = ProviderRepository(self.db).get_by_slug(record.provider)
        if registered is None or registered.id != provider_id:
            raise ValueError("Transfer-rate provider does not match persistence context")
        try:
            self.db.query(Provider.id).filter_by(id=provider_id).with_for_update().one()
            existing = (
                self.db.query(FxQuoteObservation)
                .filter_by(
                    fetch_run_id=fetch_run_id,
                    source_currency=record.source_currency,
                    target_currency=record.target_currency,
                    requested_amount=record.requested_destination_amount,
                    amount_basis="target",
                    classification="transfer_rate_observation",
                )
                .one_or_none()
            )
            if existing is not None:
                self.db.commit()
                return existing, False
            record.raw_record_id, record.fetch_run_id = raw_record_id, fetch_run_id
            row = FxQuoteObservation(
                provider_id=provider_id,
                source_currency=record.source_currency,
                target_currency=record.target_currency,
                requested_amount=record.requested_destination_amount,
                amount_basis="target",
                classification="transfer_rate_observation",
                captured_at=record.captured_at,
                expires_at=record.expires_at,
                fetch_run_id=fetch_run_id,
                raw_record_id=raw_record_id,
                response_data=record.model_dump(mode="json"),
            )
            self.db.add(row)
            self.db.commit()
            self.db.refresh(row)
            return row, True
        except Exception:
            self.db.rollback()
            raise

    def _transfer_query(self, *, provider_id, source=None, target=None):
        query = self.db.query(FxQuoteObservation).filter(
            FxQuoteObservation.provider_id == provider_id,
            FxQuoteObservation.classification == "transfer_rate_observation",
        )
        if source:
            query = query.filter(FxQuoteObservation.source_currency == source)
        if target:
            query = query.filter(FxQuoteObservation.target_currency == target)
        return query

    def get_transfer_rate(self, **scope):
        return (
            self._transfer_query(**scope)
            .order_by(
                FxQuoteObservation.captured_at.desc(),
                FxQuoteObservation.requested_amount.asc(),
                FxQuoteObservation.id.desc(),
            )
            .first()
        )

    def list_transfer_rates(self, *, provider_id, source, target, page, per_page):
        # Keep the latest observation for each exact sampled scenario visible.
        ranked = (
            self._transfer_query(
                provider_id=provider_id,
                source=source,
                target=target,
            )
            .with_entities(
                FxQuoteObservation.id.label("observation_id"),
                func.row_number()
                .over(
                    partition_by=[
                        FxQuoteObservation.source_currency,
                        FxQuoteObservation.target_currency,
                        FxQuoteObservation.requested_amount,
                    ],
                    order_by=[FxQuoteObservation.captured_at.desc(), FxQuoteObservation.id.desc()],
                )
                .label("position"),
            )
            .subquery()
        )
        query = (
            self.db.query(FxQuoteObservation)
            .join(
                ranked,
                ranked.c.observation_id == FxQuoteObservation.id,
            )
            .filter(ranked.c.position == 1)
            .order_by(
                FxQuoteObservation.source_currency,
                FxQuoteObservation.target_currency,
                FxQuoteObservation.requested_amount,
            )
        )
        return paginate_query(query, page=page, per_page=per_page)

    @staticmethod
    def transfer_rate_read(row):
        from datetime import UTC

        from app.schemas.fx import FxTransferRateRead

        captured = row.captured_at
        if captured.tzinfo is None:
            captured = captured.replace(tzinfo=UTC)
        return FxTransferRateRead.model_validate(
            {
                **row.response_data,
                "id": row.id,
                "captured_at": captured,
                "expires_at": row.expires_at,
                "raw_record_id": row.raw_record_id,
                "fetch_run_id": row.fetch_run_id,
            }
        )
