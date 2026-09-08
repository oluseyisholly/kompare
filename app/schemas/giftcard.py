from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class GiftCardVariantRead(BaseModel):
    id: int
    provider_id: int
    asset_id: int
    asset_code: str
    asset_name: str
    external_id: str
    name: str
    brand_name: str | None = None
    region: str | None = None
    source_currency: str | None = None
    card_type: str | None = None
    minimum_face_value: Decimal | None = None
    maximum_face_value: Decimal | None = None
    terms_of_transaction: str | None = None
    is_active: bool
    latest_rate_ngn: Decimal | None = None
    latest_rate_captured_at: datetime | None = None
    metadata_json: dict | None = None


class GiftCardRateRead(BaseModel):
    id: int
    provider_id: int
    giftcard_variant_id: int
    asset_code: str
    asset_name: str
    variant_name: str
    region: str | None = None
    source_currency: str | None = None
    card_type: str | None = None
    rate_value: Decimal
    rate_currency: str
    rate_unit: str
    minimum_face_value: Decimal | None = None
    maximum_face_value: Decimal | None = None
    is_active: bool
    captured_at: datetime
    last_seen_at: datetime | None = None
    superseded_at: datetime | None = None
    metadata_json: dict | None = None
