from __future__ import annotations

from decimal import Decimal
from datetime import UTC, datetime

from sqlalchemy.orm import Session, joinedload

from app.models.giftcard_rate import GiftCardRate
from app.models.enums import GiftCardRateUnit
from app.models.giftcard_variant import GiftCardVariant


class GiftCardRateRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, giftcard_rate: GiftCardRate) -> GiftCardRate:
        self.create_many([giftcard_rate])
        return self.db.query(GiftCardRate).filter(
            GiftCardRate.provider_id == giftcard_rate.provider_id,
            GiftCardRate.giftcard_variant_id == giftcard_rate.giftcard_variant_id,
            GiftCardRate.rate_currency == giftcard_rate.rate_currency,
            GiftCardRate.superseded_at.is_(None),
        ).one()

    def create_many(self, rates: list[GiftCardRate], *, commit: bool = True) -> int:
        if not rates:
            return 0
        created = 0
        try:
            self.db.query(GiftCardVariant).filter(GiftCardVariant.id.in_(
                {r.giftcard_variant_id for r in rates}
            )).order_by(GiftCardVariant.id).with_for_update().all()
            now = datetime.now(UTC)
            for rate in rates:
                rate.rate_currency = rate.rate_currency or "NGN"
                rate.rate_unit = rate.rate_unit or GiftCardRateUnit.PER_FACE_VALUE_UNIT
                if rate.is_active is None:
                    rate.is_active = True
                rate.rate_value = Decimal(str(rate.rate_value)).quantize(Decimal("0.00000001"))
                if not rate.rate_value.is_finite() or rate.rate_value <= 0:
                    raise ValueError("Gift card rate must be positive and finite")
                current = self.db.query(GiftCardRate).filter(
                    GiftCardRate.provider_id == rate.provider_id,
                    GiftCardRate.giftcard_variant_id == rate.giftcard_variant_id,
                    GiftCardRate.rate_currency == rate.rate_currency,
                    GiftCardRate.superseded_at.is_(None),
                ).first()
                fields = ("rate_value", "source_currency", "minimum_face_value", "maximum_face_value", "is_active", "rate_unit", "metadata_json")
                if current is not None and all(getattr(current, f) == getattr(rate, f) for f in fields):
                    current.last_seen_at = now
                else:
                    if current is not None:
                        current.superseded_at = now
                        self.db.flush()
                    rate.last_seen_at = now
                    self.db.add(rate)
                    created += 1
                self.db.flush()
            if commit:
                self.db.commit()
            return created
        except Exception:
            self.db.rollback()
            raise

    def get_latest_for_variant(
        self,
        *,
        giftcard_variant_id: int,
    ) -> GiftCardRate | None:
        return (
            self.db.query(GiftCardRate)
            .options(
                joinedload(GiftCardRate.provider),
                joinedload(GiftCardRate.giftcard_variant).joinedload(GiftCardVariant.asset),
            )
            .filter(GiftCardRate.giftcard_variant_id == giftcard_variant_id, GiftCardRate.superseded_at.is_(None))
            .order_by(GiftCardRate.captured_at.desc(), GiftCardRate.id.desc())
            .first()
        )

    def get_latest_matching_rate(
        self,
        *,
        provider_id: int,
        asset_id: int,
        source_currency: str,
        face_value: Decimal,
        region: str | None = None,
        card_type=None,
    ) -> GiftCardRate | None:
        query = (
            self.db.query(GiftCardRate)
            .options(
                joinedload(GiftCardRate.provider),
                joinedload(GiftCardRate.giftcard_variant).joinedload(GiftCardVariant.asset),
            )
            .join(GiftCardRate.giftcard_variant)
            .filter(
                GiftCardRate.provider_id == provider_id,
                GiftCardVariant.asset_id == asset_id,
                GiftCardRate.superseded_at.is_(None),
                GiftCardRate.source_currency == source_currency.upper(),
                GiftCardRate.is_active.is_(True),
                GiftCardVariant.is_active.is_(True),
            )
        )

        if region is not None:
            query = query.filter(GiftCardVariant.region == region)

        if card_type is not None:
            query = query.filter(GiftCardVariant.card_type == card_type)

        query = query.filter(
            (GiftCardRate.minimum_face_value.is_(None) | (GiftCardRate.minimum_face_value <= face_value)),
            (GiftCardRate.maximum_face_value.is_(None) | (GiftCardRate.maximum_face_value >= face_value)),
        )

        return query.order_by(GiftCardRate.captured_at.desc(), GiftCardRate.id.desc()).first()
