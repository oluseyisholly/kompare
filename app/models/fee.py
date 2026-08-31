from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, Integer, JSON, Numeric, String, Text, func
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.models.enums import FeeCategory, FeeType
from app.models.mixins import TimestampMixin


class FeeProfile(TimestampMixin, Base):
    __tablename__ = "fee_profiles"

    id = Column(Integer, primary_key=True, index=True)
    provider_id = Column(Integer, ForeignKey("providers.id"), nullable=False, index=True)
    title = Column(String, nullable=True)
    source_url = Column(String, nullable=True)
    source_updated_at = Column(DateTime(timezone=True), nullable=True)
    captured_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    fetch_run_id = Column(Integer, ForeignKey("fetch_runs.id"), nullable=True, index=True)
    raw_record_id = Column(Integer, ForeignKey("raw_records.id"), nullable=True, index=True)
    metadata_json = Column(JSON, nullable=True)

    provider = relationship("Provider", back_populates="fee_profiles")
    fetch_run = relationship("FetchRun", back_populates="fee_profiles")
    raw_record = relationship("RawRecord", back_populates="fee_profiles")
    rules = relationship("FeeRule", back_populates="fee_profile")


class FeeRule(TimestampMixin, Base):
    __tablename__ = "fee_rules"

    id = Column(Integer, primary_key=True, index=True)
    fee_profile_id = Column(Integer, ForeignKey("fee_profiles.id"), nullable=False, index=True)
    provider_id = Column(Integer, ForeignKey("providers.id"), nullable=False, index=True)
    provider_asset_id = Column(Integer, ForeignKey("provider_assets.id"), nullable=True, index=True)
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=True, index=True)
    fee_category = Column(Enum(FeeCategory, name="fee_category"), nullable=False, index=True)
    fee_type = Column(Enum(FeeType, name="fee_type"), nullable=False, index=True)
    from_currency = Column(String, nullable=True, index=True)
    to_currency = Column(String, nullable=True, index=True)
    value = Column(Numeric(24, 8), nullable=False)
    value_currency = Column(String, nullable=True)
    min_value = Column(Numeric(24, 8), nullable=True)
    max_value = Column(Numeric(24, 8), nullable=True)
    network = Column(String, nullable=True, index=True)
    transaction_side = Column(String, nullable=True)
    condition_text = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, server_default="true")
    captured_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    metadata_json = Column(JSON, nullable=True)

    fee_profile = relationship("FeeProfile", back_populates="rules")
    provider = relationship("Provider", back_populates="fee_rules")
    provider_asset = relationship("ProviderAsset", back_populates="fee_rules")
    asset = relationship("Asset", back_populates="fee_rules")
