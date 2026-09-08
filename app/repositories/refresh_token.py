from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models.refresh_token import RefreshToken


class RefreshTokenRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, refresh_token: RefreshToken) -> RefreshToken:
        self.db.add(refresh_token)
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
