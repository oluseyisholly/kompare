from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.fee import FeeProfile, FeeRule


class FeeProfileRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, fee_profile: FeeProfile) -> FeeProfile:
        self.db.add(fee_profile)
        self.db.commit()
        self.db.refresh(fee_profile)
        return fee_profile


class FeeRuleRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create_many(self, fee_rules: list[FeeRule]) -> int:
        if not fee_rules:
            return 0

        self.db.add_all(fee_rules)
        self.db.commit()
        return len(fee_rules)
