from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models.user import User


class UserRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_email(self, email: str) -> User | None:
        return self.db.query(User).filter(User.email == email.lower()).first()

    def get_by_id(self, user_id: int) -> User | None:
        return self.db.query(User).filter(User.id == user_id).first()

    def create(self, user: User) -> User:
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def mark_login(self, user: User) -> User:
        user.last_login_at = datetime.now(UTC)
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user
