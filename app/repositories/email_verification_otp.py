from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models.email_verification_otp import EmailVerificationOtp


class EmailVerificationOtpRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, otp: EmailVerificationOtp) -> EmailVerificationOtp:
        self.db.add(otp)
        self.db.commit()
        self.db.refresh(otp)
        return otp

    def add(self, otp: EmailVerificationOtp) -> EmailVerificationOtp:
        self.db.add(otp)
        self.db.flush()
        self.db.refresh(otp)
        return otp

    def get_active_for_user(
        self, user_id: int, *, purpose: str = "email_verification"
    ) -> EmailVerificationOtp | None:
        return (
            self.db.query(EmailVerificationOtp)
            .filter(
                EmailVerificationOtp.user_id == user_id,
                EmailVerificationOtp.purpose == purpose,
                EmailVerificationOtp.is_active.is_(True),
                EmailVerificationOtp.used_at.is_(None),
                EmailVerificationOtp.expires_at > datetime.now(UTC),
            )
            .order_by(EmailVerificationOtp.created_at.desc(), EmailVerificationOtp.id.desc())
            .first()
        )

    def deactivate_active_for_user(
        self, user_id: int, *, purpose: str = "email_verification"
    ) -> None:
        self.deactivate_active_for_user_without_commit(user_id, purpose=purpose)
        self.db.commit()

    def deactivate_active_for_user_without_commit(
        self, user_id: int, *, purpose: str = "email_verification"
    ) -> None:
        (
            self.db.query(EmailVerificationOtp)
            .filter(
                EmailVerificationOtp.user_id == user_id,
                EmailVerificationOtp.purpose == purpose,
                EmailVerificationOtp.is_active.is_(True),
                EmailVerificationOtp.used_at.is_(None),
            )
            .update({EmailVerificationOtp.is_active: False}, synchronize_session=False)
        )

    def mark_used(self, otp: EmailVerificationOtp) -> EmailVerificationOtp:
        otp.used_at = datetime.now(UTC)
        otp.is_active = False
        self.db.add(otp)
        self.db.commit()
        self.db.refresh(otp)
        return otp

    def mark_used_without_commit(self, otp: EmailVerificationOtp) -> EmailVerificationOtp:
        otp.used_at = datetime.now(UTC)
        otp.is_active = False
        self.db.add(otp)
        self.db.flush()
        self.db.refresh(otp)
        return otp
