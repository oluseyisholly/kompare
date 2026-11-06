from sqlalchemy import Column, DateTime, Enum, ForeignKey, Integer, Text
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.models.enums import UserDeletionRequestStatus
from app.models.mixins import TimestampMixin


class UserDeletionRequest(TimestampMixin, Base):
    __tablename__ = "user_deletion_requests"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    status = Column(
        Enum(UserDeletionRequestStatus, name="user_deletion_request_status"),
        nullable=False,
        index=True,
        default=UserDeletionRequestStatus.REQUESTED,
        server_default=UserDeletionRequestStatus.REQUESTED.name,
    )
    reason = Column(Text, nullable=True)
    requested_at = Column(DateTime(timezone=True), nullable=False, index=True)
    grace_ends_at = Column(DateTime(timezone=True), nullable=True, index=True)
    processing_started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)
    processed_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    admin_note = Column(Text, nullable=True)

    user = relationship("User", foreign_keys=[user_id], back_populates="deletion_requests")
    processed_by_user = relationship("User", foreign_keys=[processed_by_user_id])
