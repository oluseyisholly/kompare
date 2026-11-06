from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.models.enums import VerificationChannel, VerificationPurpose
from app.models.mixins import TimestampMixin


class VerificationOtp(TimestampMixin, Base):
    __tablename__ = "verification_otps"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    otp_hash = Column(Text, nullable=False)
    purpose = Column(
        Enum(VerificationPurpose, name="verification_purpose"), nullable=False, index=True
    )
    channel = Column(
        Enum(VerificationChannel, name="verification_channel"), nullable=False, index=True
    )
    target = Column(String, nullable=False, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    used_at = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, server_default="true", index=True)
    failed_attempts = Column(Integer, nullable=False, default=0, server_default="0")

    user = relationship("User", back_populates="verification_otps")
