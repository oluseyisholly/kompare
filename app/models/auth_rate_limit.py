"""Shared fixed-window API abuse limits; identifiers are hashed before storage."""

from sqlalchemy import Column, DateTime, Integer, String

from app.core.database import Base


class AuthRateLimit(Base):
    __tablename__ = "auth_rate_limits"

    bucket_key = Column(String(64), primary_key=True)
    attempts = Column(Integer, nullable=False)
    resets_at = Column(DateTime(timezone=True), nullable=False, index=True)
