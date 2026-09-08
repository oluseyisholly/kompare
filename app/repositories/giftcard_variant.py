from __future__ import annotations

from sqlalchemy.orm import Session, joinedload

from app.models.giftcard_variant import GiftCardVariant


class GiftCardVariantRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_provider_and_external_id(
        self,
        *,
        provider_id: int,
        external_id: str,
    ) -> GiftCardVariant | None:
        return (
            self.db.query(GiftCardVariant)
            .options(joinedload(GiftCardVariant.asset), joinedload(GiftCardVariant.provider))
            .filter(
                GiftCardVariant.provider_id == provider_id,
                GiftCardVariant.external_id == external_id,
            )
            .first()
        )

    def list_by_provider_id(self, provider_id: int) -> list[GiftCardVariant]:
        return (
            self.db.query(GiftCardVariant)
            .options(joinedload(GiftCardVariant.asset), joinedload(GiftCardVariant.provider))
            .filter(GiftCardVariant.provider_id == provider_id)
            .order_by(GiftCardVariant.name.asc(), GiftCardVariant.id.asc())
            .all()
        )

    def upsert(
        self,
        *,
        provider_id: int,
        asset_id: int,
        external_id: str,
        name: str,
        brand_name: str | None = None,
        region: str | None = None,
        source_currency: str | None = None,
        card_type=None,
        minimum_face_value=None,
        maximum_face_value=None,
        terms_of_transaction: str | None = None,
        is_active: bool = True,
        metadata_json: dict | None = None,
    ) -> GiftCardVariant:
        row = self.get_by_provider_and_external_id(
            provider_id=provider_id,
            external_id=external_id,
        )
        if row is None:
            row = GiftCardVariant(
                provider_id=provider_id,
                asset_id=asset_id,
                external_id=external_id,
                name=name,
                brand_name=brand_name,
                region=region,
                source_currency=source_currency,
                card_type=card_type,
                minimum_face_value=minimum_face_value,
                maximum_face_value=maximum_face_value,
                terms_of_transaction=terms_of_transaction,
                is_active=is_active,
                metadata_json=metadata_json,
            )
            self.db.add(row)
            self.db.commit()
            self.db.refresh(row)
            return row

        row.asset_id = asset_id
        row.name = name
        row.brand_name = brand_name
        row.region = region
        row.source_currency = source_currency
        row.card_type = card_type
        row.minimum_face_value = minimum_face_value
        row.maximum_face_value = maximum_face_value
        row.terms_of_transaction = terms_of_transaction
        row.is_active = is_active
        row.metadata_json = metadata_json
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row
