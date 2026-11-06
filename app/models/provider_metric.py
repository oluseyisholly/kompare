from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.models.mixins import TimestampMixin


class ProviderMetric(TimestampMixin, Base):
    __tablename__ = "provider_metrics"

    id = Column(Integer, primary_key=True, index=True)
    provider_id = Column(
        Integer, ForeignKey("providers.id"), nullable=False, unique=True, index=True
    )
    average_rating = Column(Numeric(4, 2), nullable=True)
    review_count = Column(Integer, nullable=False, default=0, server_default="0")
    feed_health = Column(String, nullable=False, default="unknown", server_default="unknown")
    coverage_score = Column(Integer, nullable=False, default=0, server_default="0")
    last_synced_at = Column(DateTime(timezone=True), nullable=True)
    last_successful_run_at = Column(DateTime(timezone=True), nullable=True)
    last_failed_run_at = Column(DateTime(timezone=True), nullable=True)
    last_error_message = Column(Text, nullable=True)

    provider = relationship("Provider", back_populates="metrics")
