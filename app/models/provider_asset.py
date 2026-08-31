from sqlalchemy import Boolean, Column, Enum, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.models.enums import ProviderName
from app.models.mixins import TimestampMixin


class ProviderAsset(TimestampMixin, Base):
    __tablename__ = "provider_assets"
    __table_args__ = (
        UniqueConstraint("provider", "provider_symbol", name="uq_provider_asset_symbol"),
    )

    id = Column(Integer, primary_key=True, index=True)
    provider = Column(Enum(ProviderName, name="provider_name"), nullable=False, index=True)
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=False, index=True)
    provider_symbol = Column(String, nullable=False, index=True)
    provider_name = Column(String, nullable=True)
    metadata_json = Column(JSON, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, server_default="true")

    asset = relationship("Asset", back_populates="provider_assets")
    quotes = relationship("Quote", back_populates="provider_asset")
    fee_rules = relationship("FeeRule", back_populates="provider_asset")
