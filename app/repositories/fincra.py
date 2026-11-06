"""Side-preserving treasury feed persistence and local reads."""

from datetime import UTC
from decimal import Decimal

from sqlalchemy import func

from app.models.asset import Asset
from app.models.enums import MarketCategory, ProviderName, QuoteType
from app.models.provider import Provider
from app.models.quote import Quote, QuoteObservation
from app.repositories.pagination import paginate_query
from app.repositories.quote import QuoteRepository
from app.schemas.fx import FxCurrencyRead, FxTreasuryRateRead
from app.utils.currency_precision import currency_precision


class FincraRepository:
    def __init__(self, db):
        self.db = db

    def query(self, *, current=True):
        query = self.db.query(Quote).filter(
            Quote.provider == ProviderName.FINCRA,
            Quote.metadata_json["classification"].as_string() == "treasury_rate",
        )
        return query.filter(Quote.superseded_at.is_(None)) if current else query

    def persist(self, records, *, provider_id, run_id, captured_at):
        # records contain parsed rates plus page-specific raw provenance.
        try:
            self.db.query(Provider.id).filter_by(id=provider_id).with_for_update().one()
            latest = (
                self.db.query(func.max(QuoteObservation.fetch_run_id))
                .join(Quote, Quote.id == QuoteObservation.quote_id)
                .filter(Quote.provider == ProviderName.FINCRA)
                .scalar()
            )
            if latest is not None and latest > run_id:
                self.db.commit()
                return {
                    "status": "skipped",
                    "rates_observed": 0,
                    "versions_created": 0,
                    "skip_reason": "newer_rate_snapshot_already_applied",
                }
            codes = sorted({item[0].baseCurrency for item in records})
            assets = {a.code: a for a in self.db.query(Asset).filter(Asset.code.in_(codes)).all()}
            for code in codes:
                if code not in assets:
                    assets[code] = Asset(
                        code=code, name=code, category=MarketCategory.FX, is_active=True
                    )
                    self.db.add(assets[code])
                if assets[code].category != MarketCategory.FX:
                    raise ValueError("Asset category conflict")
            self.db.flush()
            self.db.query(Asset.id).filter(
                Asset.id.in_([assets[code].id for code in codes])
            ).order_by(Asset.id).with_for_update().all()
            keys, quotes = set(), []
            for record, raw_id, source_url, feed_time in records:
                kind = QuoteType.BUY if record.side == "buy" else QuoteType.SELL
                keys.add((record.baseCurrency, record.quoteCurrency, kind))
                quotes.append(
                    Quote(
                        provider=ProviderName.FINCRA,
                        asset_id=assets[record.baseCurrency].id,
                        quote_type=kind,
                        base_currency=record.baseCurrency,
                        quote_currency=record.quoteCurrency,
                        market_price=record.price,
                        fetch_run_id=run_id,
                        raw_record_id=raw_id,
                        captured_at=captured_at,
                        metadata_json={
                            "classification": "treasury_rate",
                            "provider_price": str(record.price),
                            "side": record.side,
                            "source_url": source_url,
                            "feed_timestamp": feed_time.isoformat() if feed_time else None,
                            "side_perspective": "unverified",
                        },
                    )
                )
            for old in self.query().populate_existing().all():
                if (old.base_currency, old.quote_currency, old.quote_type) not in keys:
                    old.superseded_at = captured_at
            # Same transaction for snapshot retirement and price-history writes.
            created = QuoteRepository(self.db).create_many(
                quotes, observation_metadata_keys=frozenset({"feed_timestamp", "source_url"})
            )
            return {
                "status": "success",
                "rates_observed": len(records),
                "versions_created": created,
            }
        except Exception:
            self.db.rollback()
            raise

    @staticmethod
    def read(row):
        meta = row.metadata_json

        def aware(value):
            return value.replace(tzinfo=UTC) if value.tzinfo is None else value

        return FxTreasuryRateRead(
            id=row.id,
            provider="fincra",
            source_currency=row.base_currency,
            target_currency=row.quote_currency,
            rate=Decimal(meta["provider_price"]),
            side=meta["side"],
            captured_at=aware(row.captured_at),
            last_seen_at=aware(row.last_seen_at),
            feed_timestamp=meta.get("feed_timestamp"),
            source_url=meta["source_url"],
            raw_record_id=row.raw_record_id,
        )

    def list_rates(self, *, source, target, page, per_page):
        query = self.query()
        if source:
            query = query.filter(Quote.base_currency == source)
        if target:
            query = query.filter(Quote.quote_currency == target)
        rows, total = paginate_query(
            query.order_by(Quote.base_currency, Quote.quote_currency, Quote.quote_type),
            page=page,
            per_page=per_page,
        )
        return [self.read(row) for row in rows], total

    def get_rate(self, source, target, side):
        return (
            self.query()
            .filter(
                Quote.base_currency == source,
                Quote.quote_currency == target,
                Quote.quote_type == (QuoteType.BUY if side == "buy" else QuoteType.SELL),
            )
            .one_or_none()
        )

    def currencies(self, *, page, per_page):
        # Observed feed membership, not a fabricated official transfer catalogue.
        rows = self.query().order_by(Quote.captured_at.desc(), Quote.id.desc()).all()
        by_code = {}
        for row in rows:
            for code in (row.base_currency, row.quote_currency):
                by_code.setdefault(code, row)
        result = []
        for code in sorted(by_code)[(page - 1) * per_page : page * per_page]:
            row = by_code[code]
            places, source = currency_precision(code)
            result.append(
                FxCurrencyRead(
                    id=None,
                    provider="fincra",
                    code=code,
                    name=None,
                    symbol=None,
                    supports_decimals=None,
                    country_keywords=[],
                    decimal_places=places,
                    precision_source=source,
                    captured_at=row.captured_at,
                    source_url=row.metadata_json["source_url"],
                    raw_record_id=row.raw_record_id,
                    discovery_basis="observed_rate_pairs",
                )
            )
        return result, len(by_code)
