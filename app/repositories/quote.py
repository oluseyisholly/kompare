from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy.orm import Session

from app.models.asset import Asset
from app.models.quote import Quote, QuoteObservation


class QuoteRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create_many(self, quotes: list[Quote]) -> int:
        if not quotes:
            return 0
        created = 0
        try:
            # Lock existing parent rows even when a pair has no quote yet. Stable
            # ordering avoids deadlocks between concurrent ingestion batches.
            self.db.query(Asset).filter(
                Asset.id.in_({q.asset_id for q in quotes})
            ).order_by(Asset.id).with_for_update().all()
            observed_at = datetime.now(UTC)
            for incoming in quotes:
                for field in ("buy_rate", "sell_rate", "mid_rate", "market_price"):
                    value = getattr(incoming, field)
                    if value is not None:
                        value = Decimal(str(value))
                        if not value.is_finite() or value < 0:
                            raise ValueError(f"Invalid quote {field}")
                        setattr(incoming, field, value.quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP))
                current = self.db.query(Quote).filter(
                    Quote.provider == incoming.provider,
                    Quote.asset_id == incoming.asset_id,
                    Quote.base_currency == incoming.base_currency,
                    Quote.quote_currency == incoming.quote_currency,
                    Quote.quote_type == incoming.quote_type,
                    Quote.superseded_at.is_(None),
                ).first()
                if current is not None and self._same_offer(current, incoming):
                    current.last_seen_at = observed_at
                    selected = current
                else:
                    if current is not None:
                        current.superseded_at = observed_at
                        self.db.flush()
                    incoming.last_seen_at = observed_at
                    self.db.add(incoming)
                    self.db.flush()
                    selected = incoming
                    created += 1
                self.db.add(QuoteObservation(
                    quote_id=selected.id, fetch_run_id=incoming.fetch_run_id,
                    raw_record_id=incoming.raw_record_id, observed_at=observed_at,
                ))
                self.db.flush()
            self.db.commit()
            return created
        except Exception:
            self.db.rollback()
            raise

    @staticmethod
    def _same_offer(current: Quote, incoming: Quote) -> bool:
        fields = ("buy_rate", "sell_rate", "mid_rate", "market_price", "provider_asset_id")
        # Rolling market statistics stay in raw records, not in the offer identity.
        ignored = {"high", "low", "open", "volume", "percentage_change"}
        def conditions(quote):
            return {k: v for k, v in (quote.metadata_json or {}).items() if k not in ignored}
        return all(getattr(current, f) == getattr(incoming, f) for f in fields) and conditions(current) == conditions(incoming)
