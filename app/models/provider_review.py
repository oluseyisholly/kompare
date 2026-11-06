from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.models.enums import (
    ProviderReviewStatus,
    ProviderReviewType,
    ProviderTipCategory,
    ProviderTipSeverity,
)
from app.models.mixins import TimestampMixin


class ProviderReview(TimestampMixin, Base):
    __tablename__ = "provider_reviews"

    id = Column(Integer, primary_key=True, index=True)
    provider_id = Column(Integer, ForeignKey("providers.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    review_type = Column(
        Enum(ProviderReviewType, name="provider_review_type"),
        nullable=False,
        index=True,
        default=ProviderReviewType.REVIEW,
        server_default=ProviderReviewType.REVIEW.name,
    )
    tip_category = Column(
        Enum(ProviderTipCategory, name="provider_tip_category"), nullable=True, index=True
    )
    tip_severity = Column(
        Enum(ProviderTipSeverity, name="provider_tip_severity"), nullable=True, index=True
    )
    rating = Column(Integer, nullable=True)
    title = Column(String, nullable=True)
    body = Column(Text, nullable=False)
    tags = Column(JSON, nullable=False, default=list)
    is_verified = Column(Boolean, nullable=False, default=False, server_default="false", index=True)
    status = Column(
        Enum(ProviderReviewStatus, name="provider_review_status"),
        nullable=False,
        index=True,
        default=ProviderReviewStatus.PENDING,
    )
    reviewed_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )

    provider = relationship("Provider", back_populates="reviews")
    user = relationship("User", back_populates="provider_reviews")
    comments = relationship("ProviderReviewComment", back_populates="review")
    votes = relationship("ProviderReviewVote", back_populates="review")

    __table_args__ = (
        CheckConstraint("rating >= 1 AND rating <= 5", name="ck_provider_reviews_rating_range"),
        CheckConstraint(
            """
            (
                review_type = 'REVIEW'
                AND rating IS NOT NULL
                AND title IS NOT NULL
                AND tip_category IS NULL
                AND tip_severity IS NULL
            )
            OR
            (
                review_type = 'TIP'
                AND rating IS NULL
                AND title IS NULL
                AND tip_category IS NOT NULL
                AND tip_severity IS NOT NULL
            )
            """,
            name="ck_provider_reviews_review_tip_shape",
        ),
        Index(
            "ix_provider_reviews_provider_status_reviewed_at",
            "provider_id",
            "status",
            "reviewed_at",
        ),
    )


class ProviderReviewComment(TimestampMixin, Base):
    __tablename__ = "provider_review_comments"

    id = Column(Integer, primary_key=True, index=True)
    review_id = Column(Integer, ForeignKey("provider_reviews.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    body = Column(Text, nullable=False)
    status = Column(
        Enum(ProviderReviewStatus, name="provider_review_status"),
        nullable=False,
        index=True,
        default=ProviderReviewStatus.PENDING,
    )

    review = relationship("ProviderReview", back_populates="comments")
    user = relationship("User", back_populates="provider_review_comments")


class ProviderReviewVote(TimestampMixin, Base):
    __tablename__ = "provider_review_votes"

    id = Column(Integer, primary_key=True, index=True)
    review_id = Column(Integer, ForeignKey("provider_reviews.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    is_helpful = Column(Boolean, nullable=False, index=True)

    review = relationship("ProviderReview", back_populates="votes")
    user = relationship("User", back_populates="provider_review_votes")

    __table_args__ = (
        UniqueConstraint("review_id", "user_id", name="uq_provider_review_votes_review_user"),
    )
