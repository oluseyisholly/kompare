from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, Index, Integer, JSON, Numeric, String, func
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.models.enums import GiftCardRateUnit
from app.models.mixins import TimestampMixin


class GiftCardRate(TimestampMixin, Base):
    __tablename__ = "giftcard_rates"

    id = Column(Integer, primary_key=True, index=True)
    provider_id = Column(Integer, ForeignKey("providers.id"), nullable=False, index=True)
    giftcard_variant_id = Column(Integer, ForeignKey("giftcard_variants.id"), nullable=False, index=True)
    fetch_run_id = Column(Integer, ForeignKey("fetch_runs.id"), nullable=True, index=True)
    raw_record_id = Column(Integer, ForeignKey("raw_records.id"), nullable=True, index=True)
    rate_value = Column(Numeric(24, 8), nullable=False)
    rate_currency = Column(String, nullable=False, index=True, default="NGN", server_default="NGN")
    rate_unit = Column(
        Enum(GiftCardRateUnit, name="giftcard_rate_unit"),
        nullable=False,
        index=True,
        default=GiftCardRateUnit.PER_FACE_VALUE_UNIT,
        server_default=GiftCardRateUnit.PER_FACE_VALUE_UNIT.name,
    )
    source_currency = Column(String, nullable=True, index=True)
    minimum_face_value = Column(Numeric(24, 8), nullable=True)
    maximum_face_value = Column(Numeric(24, 8), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, server_default="true")
    captured_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)
    last_seen_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    superseded_at = Column(DateTime(timezone=True), nullable=True)
    metadata_json = Column(JSON, nullable=True)

    provider = relationship("Provider", back_populates="giftcard_rates")
    giftcard_variant = relationship("GiftCardVariant", back_populates="rates")
    fetch_run = relationship("FetchRun", back_populates="giftcard_rates")
    raw_record = relationship("RawRecord", back_populates="giftcard_rates")


Index("uq_giftcard_rates_current", GiftCardRate.provider_id, GiftCardRate.giftcard_variant_id,
      GiftCardRate.rate_currency, unique=True,
      postgresql_where=GiftCardRate.superseded_at.is_(None),
      sqlite_where=GiftCardRate.superseded_at.is_(None))
