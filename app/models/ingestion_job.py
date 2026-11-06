"""Durable ingestion requests shared by API replicas and worker processes."""

from sqlalchemy import Boolean, Column, DateTime, Index, Integer, String, Text, func

from app.core.database import Base
from app.models.mixins import TimestampMixin


class IngestionJob(TimestampMixin, Base):
    __tablename__ = "ingestion_jobs"

    id = Column(Integer, primary_key=True)
    provider_slug = Column(String(64), nullable=True)
    job_type = Column(String(32), nullable=False)
    include_kyc = Column(Boolean, nullable=False, default=False, server_default="false")
    status = Column(String(16), nullable=False, default="pending", server_default="pending")
    attempts = Column(Integer, nullable=False, default=0, server_default="0")
    lease_token = Column(String(64), nullable=True)
    leased_until = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    error_message = Column(Text, nullable=True)
    queued_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


Index("ix_ingestion_jobs_claim", IngestionJob.status, IngestionJob.leased_until, IngestionJob.id)
