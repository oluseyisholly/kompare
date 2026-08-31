from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.quote import Quote


class QuoteRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create_many(self, quotes: list[Quote]) -> int:
        if not quotes:
            return 0
        self.db.add_all(quotes)
        self.db.commit()
        return len(quotes)
