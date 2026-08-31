from sqlalchemy import Column, DateTime, Enum, Integer, JSON, String, func
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.models.enums import FetchRunStatus, ProviderName
from app.models.mixins import TimestampMixin


class FetchRun(TimestampMixin, Base):
    __tablename__ = "fetch_runs"

    id = Column(Integer, primary_key=True, index=True)
    provider = Column(Enum(ProviderName, name="provider_name"), nullable=False, index=True)
    status = Column(Enum(FetchRunStatus, name="fetch_run_status"), nullable=False, index=True)
    started_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    finished_at = Column(DateTime(timezone=True), nullable=True)
    error_message = Column(String, nullable=True)
    records_fetched = Column(Integer, nullable=False, default=0, server_default="0")
    metadata_json = Column(JSON, nullable=True)

    raw_records = relationship("RawRecord", back_populates="fetch_run")
    quotes = relationship("Quote", back_populates="fetch_run")
    kyc_profiles = relationship("KycProfile", back_populates="fetch_run")
    fee_profiles = relationship("FeeProfile", back_populates="fetch_run")
