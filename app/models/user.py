from sqlalchemy import Boolean, Column, DateTime, Enum, Integer, String
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.models.enums import AdminType, UserRole, UserStatus
from app.models.mixins import TimestampMixin


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    auth_version = Column(Integer, nullable=False, default=0, server_default="0")
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    phone_number = Column(String, nullable=True, index=True)
    is_phone_verified = Column(Boolean, nullable=False, default=False, server_default="false")
    role = Column(Enum(UserRole, name="user_role"), nullable=False, index=True)
    admin_type = Column(Enum(AdminType, name="admin_type"), nullable=True, index=True)
    status = Column(
        Enum(UserStatus, name="user_status"),
        nullable=False,
        index=True,
        default=UserStatus.UNVERIFIED,
        server_default=UserStatus.UNVERIFIED.name,
    )
    is_superadmin = Column(Boolean, nullable=False, default=False, server_default="false")
    is_active = Column(Boolean, nullable=False, default=True, server_default="true")
    is_verified = Column(Boolean, nullable=False, default=False, server_default="false")
    last_login_at = Column(DateTime(timezone=True), nullable=True)
    suspended_at = Column(DateTime(timezone=True), nullable=True)
    suspended_reason = Column(String, nullable=True)

    email_verification_otps = relationship("EmailVerificationOtp", back_populates="user")
    verification_otps = relationship("VerificationOtp", back_populates="user")
    refresh_tokens = relationship("RefreshToken", back_populates="user")
    provider_reviews = relationship("ProviderReview", back_populates="user")
    provider_review_comments = relationship("ProviderReviewComment", back_populates="user")
    provider_review_votes = relationship("ProviderReviewVote", back_populates="user")
    audit_logs = relationship("AuditLog", back_populates="actor_user")
    deletion_requests = relationship(
        "UserDeletionRequest",
        foreign_keys="UserDeletionRequest.user_id",
        back_populates="user",
    )
