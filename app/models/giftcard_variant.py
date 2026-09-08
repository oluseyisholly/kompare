from sqlalchemy import Boolean, Column, Enum, ForeignKey, Integer, JSON, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.models.enums import GiftCardType
from app.models.mixins import TimestampMixin


class GiftCardVariant(TimestampMixin, Base):
    __tablename__ = "giftcard_variants"
    __table_args__ = (
        UniqueConstraint("provider_id", "external_id", name="uq_giftcard_variants_provider_external_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    provider_id = Column(Integer, ForeignKey("providers.id"), nullable=False, index=True)
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=False, index=True)
    external_id = Column(String, nullable=False, index=True)
    name = Column(String, nullable=False)
    brand_name = Column(String, nullable=True)
    region = Column(String, nullable=True, index=True)
    source_currency = Column(String, nullable=True, index=True)
    card_type = Column(Enum(GiftCardType, name="giftcard_type"), nullable=True, index=True)
    minimum_face_value = Column(Numeric(24, 8), nullable=True)
    maximum_face_value = Column(Numeric(24, 8), nullable=True)
    terms_of_transaction = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, server_default="true")
    metadata_json = Column(JSON, nullable=True)

    provider = relationship("Provider", back_populates="giftcard_variants")
    asset = relationship("Asset", back_populates="giftcard_variants")
    rates = relationship("GiftCardRate", back_populates="giftcard_variant")
