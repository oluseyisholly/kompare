from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models.enums import VerificationChannel, VerificationPurpose
from app.models.verification_otp import VerificationOtp


class VerificationOtpRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def add(self, otp: VerificationOtp) -> VerificationOtp:
        self.db.add(otp)
        self.db.flush()
        self.db.refresh(otp)
        return otp

    def get_latest_for_user(
        self, user_id: int, *, purpose: VerificationPurpose, channel: VerificationChannel
    ) -> VerificationOtp | None:
        return (
            self.db.query(VerificationOtp)
            .filter_by(user_id=user_id, purpose=purpose, channel=channel)
            .order_by(VerificationOtp.created_at.desc(), VerificationOtp.id.desc())
            .first()
        )

    def get_active_for_user(
        self,
        user_id: int,
        *,
        purpose: VerificationPurpose,
        channel: VerificationChannel,
        target: str | None = None,
        for_update: bool = False,
    ) -> VerificationOtp | None:
        query = self.db.query(VerificationOtp).filter(
            VerificationOtp.user_id == user_id,
            VerificationOtp.purpose == purpose,
            VerificationOtp.channel == channel,
            VerificationOtp.is_active.is_(True),
            VerificationOtp.used_at.is_(None),
            VerificationOtp.expires_at > datetime.now(UTC),
        )
        if target is not None:
            query = query.filter(VerificationOtp.target == target)
        if for_update:
            query = query.with_for_update().populate_existing()
        return query.order_by(VerificationOtp.created_at.desc(), VerificationOtp.id.desc()).first()

    def deactivate_active_for_user_without_commit(
        self,
        user_id: int,
        *,
        purpose: VerificationPurpose,
        channel: VerificationChannel,
        target: str | None = None,
    ) -> None:
        query = self.db.query(VerificationOtp).filter(
            VerificationOtp.user_id == user_id,
            VerificationOtp.purpose == purpose,
            VerificationOtp.channel == channel,
            VerificationOtp.is_active.is_(True),
            VerificationOtp.used_at.is_(None),
        )
        if target is not None:
            query = query.filter(VerificationOtp.target == target)
        query.update({VerificationOtp.is_active: False}, synchronize_session=False)

    def mark_used_without_commit(self, otp: VerificationOtp) -> VerificationOtp:
        otp.used_at = datetime.now(UTC)
        otp.is_active = False
        self.db.add(otp)
        self.db.flush()
        self.db.refresh(otp)
        return otp
