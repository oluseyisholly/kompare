from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models.refresh_token import RefreshToken


class RefreshTokenRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, refresh_token: RefreshToken, *, commit: bool = True) -> RefreshToken:
        self.db.add(refresh_token)
        self.db.flush()
        if commit:
            self.db.commit()
        self.db.refresh(refresh_token)
        return refresh_token

    def get_active_by_token_id(self, token_id: str) -> RefreshToken | None:
        return (
            self.db.query(RefreshToken)
            .filter(
                RefreshToken.token_id == token_id,
                RefreshToken.is_active.is_(True),
                RefreshToken.revoked_at.is_(None),
            )
            .first()
        )

    def revoke(self, refresh_token: RefreshToken) -> RefreshToken:
        refresh_token.is_active = False
        refresh_token.revoked_at = datetime.now(UTC)
        self.db.add(refresh_token)
        self.db.commit()
        self.db.refresh(refresh_token)
        return refresh_token

    def consume(self, *, token_id, token_hash, user_id, now):
        # Conditional UPDATE admits one consumer even across separate workers.
        return (
            self.db.query(RefreshToken)
            .filter(
                RefreshToken.token_id == token_id,
                RefreshToken.user_id == user_id,
                RefreshToken.token_hash == token_hash,
                RefreshToken.is_active.is_(True),
                RefreshToken.revoked_at.is_(None),
                RefreshToken.expires_at > now,
            )
            .update(
                {RefreshToken.is_active: False, RefreshToken.revoked_at: now},
                synchronize_session=False,
            )
            == 1
        )

    def revoke_all_for_user_without_commit(self, user_id: int) -> None:
        self.db.query(RefreshToken).filter(
            RefreshToken.user_id == user_id,
            RefreshToken.is_active.is_(True),
        ).update(
            {RefreshToken.is_active: False, RefreshToken.revoked_at: datetime.now(UTC)},
            synchronize_session=False,
        )
