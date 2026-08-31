from sqlalchemy import Boolean, Column, Enum, Integer, JSON, String
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.models.enums import MarketCategory
from app.models.mixins import TimestampMixin


class Asset(TimestampMixin, Base):
    __tablename__ = "assets"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    code = Column(String, unique=True, nullable=False, index=True)
    category = Column(Enum(MarketCategory, name="market_category"), nullable=False, index=True)
    metadata_json = Column(JSON, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, server_default="true")

    provider_assets = relationship("ProviderAsset", back_populates="asset")
    quotes = relationship("Quote", back_populates="asset")
    fee_rules = relationship("FeeRule", back_populates="asset")
