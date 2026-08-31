from sqlalchemy import Column, DateTime, Enum, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.models.enums import ProviderName
from app.models.mixins import TimestampMixin


class KycProfile(TimestampMixin, Base):
    __tablename__ = "kyc_profiles"

    id = Column(Integer, primary_key=True, index=True)
    provider = Column(Enum(ProviderName, name="provider_name"), nullable=False, index=True)
    title = Column(String, nullable=False)
    source_url = Column(String, nullable=False)
    source_updated_at = Column(DateTime(timezone=True), nullable=True)
    fetched_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    fetch_run_id = Column(Integer, ForeignKey("fetch_runs.id"), nullable=True, index=True)
    raw_record_id = Column(Integer, ForeignKey("raw_records.id"), nullable=True, index=True)

    fetch_run = relationship("FetchRun", back_populates="kyc_profiles")
    raw_record = relationship("RawRecord", back_populates="kyc_profiles")
    levels = relationship("KycLevel", back_populates="kyc_profile")


class KycLevel(TimestampMixin, Base):
    __tablename__ = "kyc_levels"

    id = Column(Integer, primary_key=True, index=True)
    kyc_profile_id = Column(Integer, ForeignKey("kyc_profiles.id"), nullable=False, index=True)
    level_name = Column(String, nullable=False)
    rank = Column(Integer, nullable=False)
    description = Column(Text, nullable=True)
    limit_reference = Column(String, nullable=True)
    exchange_limit_text = Column(Text, nullable=True)
    exchange_limit_period = Column(String, nullable=True)
    fiat_deposit_limit = Column(String, nullable=True)
    fiat_withdrawal_limit = Column(String, nullable=True)
    crypto_deposit_limit = Column(String, nullable=True)
    crypto_withdrawal_limit = Column(String, nullable=True)
    requirements = Column(JSON, nullable=True)
    notes = Column(Text, nullable=True)
    metadata_json = Column(JSON, nullable=True)

    kyc_profile = relationship("KycProfile", back_populates="levels")
