from sqlalchemy import Column, DateTime, Enum, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.models.enums import ProviderName, RawSourceType
from app.models.mixins import TimestampMixin


class RawRecord(TimestampMixin, Base):
    __tablename__ = "raw_records"

    id = Column(Integer, primary_key=True, index=True)
    provider = Column(Enum(ProviderName, name="provider_name"), nullable=False, index=True)
    fetch_run_id = Column(Integer, ForeignKey("fetch_runs.id"), nullable=False, index=True)
    source_type = Column(Enum(RawSourceType, name="raw_source_type"), nullable=False, index=True)
    source_url = Column(String, nullable=True)
    external_id = Column(String, nullable=True, index=True)
    payload = Column(JSON, nullable=True)
    raw_text = Column(Text, nullable=True)
    fetched_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    fetch_run = relationship("FetchRun", back_populates="raw_records")
    quotes = relationship("Quote", back_populates="raw_record")
    kyc_profiles = relationship("KycProfile", back_populates="raw_record")
    fee_profiles = relationship("FeeProfile", back_populates="raw_record")
