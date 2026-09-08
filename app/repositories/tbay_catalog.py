from datetime import UTC, datetime

from app.models.asset import Asset
from app.models.enums import FetchRunStatus, GiftCardRateUnit, MarketCategory, ProviderName, RawSourceType
from app.models.giftcard_rate import GiftCardRate
from app.models.giftcard_variant import GiftCardVariant
from app.models.provider import Provider
from app.models.raw_record import RawRecord


class TbayCatalogRepository:
    def __init__(self, db, rate_repository):
        self.db = db
        self.rate_repository = rate_repository

    def persist(self, *, run, categories, batches, points_payload, source_url, finalize=True):
        try:
            provider = self.db.query(Provider).filter(Provider.slug == "tbay").with_for_update().one()
            rates = []
            seen = set()
            for batch in batches:
                raw = RawRecord(provider=ProviderName.TBAY, fetch_run_id=run.id,
                    source_type=RawSourceType.API, source_url=source_url,
                    payload={"category": batch["category"], "currency": batch["currency"],
                             "offers": batch["offers"], "points_rate": points_payload,
                             "sanitized": True})
                self.db.add(raw)
                self.db.flush()
                for row in batch["normalized"]:
                    if row["external_id"] in seen:
                        raise ValueError("Duplicate Tbay offer across catalog scopes")
                    seen.add(row["external_id"])
                    asset = self.db.query(Asset).filter(Asset.code == row["asset_code"]).first()
                    if asset is None:
                        asset = Asset(code=row["asset_code"], name=row["brand"], category=MarketCategory.GIFTCARD)
                        self.db.add(asset)
                        self.db.flush()
                    elif asset.category != MarketCategory.GIFTCARD:
                        raise ValueError("Tbay brand conflicts with a non-gift-card asset")
                    variant = self.db.query(GiftCardVariant).filter(
                        GiftCardVariant.provider_id == provider.id,
                        GiftCardVariant.external_id == row["external_id"]).first()
                    if variant is None:
                        variant = GiftCardVariant(provider_id=provider.id, external_id=row["external_id"])
                        self.db.add(variant)
                    variant.asset_id = asset.id
                    variant.name = row["name"]
                    variant.brand_name = row["brand"]
                    variant.source_currency = row["source_currency"]
                    variant.minimum_face_value = row["minimum"]
                    variant.maximum_face_value = row["maximum"]
                    variant.terms_of_transaction = row["terms"]
                    variant.is_active = row["active"]
                    variant.metadata_json = {**row["conditions"], "tbay_category_id": batch["category"]["code"]}
                    self.db.flush()
                    rates.append(GiftCardRate(provider_id=provider.id, giftcard_variant_id=variant.id,
                        fetch_run_id=run.id, raw_record_id=raw.id, rate_value=row["rate"], rate_currency="NGN",
                        rate_unit=GiftCardRateUnit.PER_FACE_VALUE_UNIT, source_currency=row["source_currency"],
                        minimum_face_value=row["minimum"], maximum_face_value=row["maximum"],
                        is_active=row["active"], captured_at=batch["captured_at"], metadata_json=row["conditions"]))
            created = self.rate_repository.create_many(rates, commit=False)
            # Retire only offers belonging to a successfully fetched scope.
            # Legacy variants without category metadata are retained conservatively.
            completed_scopes = {(b["category"]["code"], b["currency"]) for b in batches}
            missing = self.db.query(GiftCardVariant).filter(
                GiftCardVariant.provider_id == provider.id, ~GiftCardVariant.external_id.in_(seen)).all()
            for variant in missing:
                scope = ((variant.metadata_json or {}).get("tbay_category_id"), variant.source_currency)
                if scope in completed_scopes:
                    variant.is_active = False
            if finalize:
                run.status = FetchRunStatus.SUCCESS
                run.finished_at = datetime.now(UTC)
                run.records_fetched = len(seen)
            self.db.commit()
            return {"fetch_run_id": run.id, "categories_processed": len(categories),
                    "variants_processed": len(seen), "rates_created": created, "raw_records_created": len(batches)}
        except Exception:
            self.db.rollback()
            raise
