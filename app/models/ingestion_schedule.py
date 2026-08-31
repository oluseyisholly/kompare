from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.models.enums import IngestionJobType
from app.models.mixins import TimestampMixin


class IngestionSchedule(TimestampMixin, Base):
    __tablename__ = "ingestion_schedules"
    __table_args__ = (
        UniqueConstraint("provider_id", "job_type", name="uq_ingestion_schedules_provider_job_type"),
    )

    id = Column(Integer, primary_key=True, index=True)
    provider_id = Column(Integer, ForeignKey("providers.id"), nullable=False, index=True)
    job_type = Column(Enum(IngestionJobType, name="ingestion_job_type"), nullable=False, index=True)
    interval_minutes = Column(Integer, nullable=False)
    is_enabled = Column(Boolean, nullable=False, default=True, server_default="true")
    next_run_at = Column(DateTime(timezone=True), nullable=True)
    last_run_at = Column(DateTime(timezone=True), nullable=True)
    notes = Column(String, nullable=True)
    metadata_json = Column(JSON, nullable=True)

    provider = relationship("Provider", back_populates="ingestion_schedules")
