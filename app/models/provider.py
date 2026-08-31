from sqlalchemy import Boolean, Column, Enum, Integer, JSON, String, Text
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.models.enums import MarketCategory
from app.models.mixins import TimestampMixin


class Provider(TimestampMixin, Base):
    __tablename__ = "providers"

    id = Column(Integer, primary_key=True, index=True)
    slug = Column(String, unique=True, nullable=False, index=True)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    logo_url = Column(String, nullable=True)
    website_url = Column(String, nullable=True)
    category = Column(Enum(MarketCategory, name="market_category"), nullable=False, index=True)
    is_active = Column(Boolean, nullable=False, default=True, server_default="true")
    has_adapter = Column(Boolean, nullable=False, default=False, server_default="false")
    metadata_json = Column(JSON, nullable=True)

    fee_profiles = relationship("FeeProfile", back_populates="provider")
    fee_rules = relationship("FeeRule", back_populates="provider")
