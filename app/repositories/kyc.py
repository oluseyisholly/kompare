from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models.enums import ProviderName
from app.models.fetch_run import FetchRun
from app.models.kyc import KycLevel, KycProfile
from app.models.raw_record import RawRecord


class KycRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create_manual_profile(
        self,
        *,
        provider: ProviderName,
        title: str,
        source_url: str,
        source_updated_at: datetime | None,
        fetched_at: datetime | None,
        levels: list[dict],
    ) -> KycProfile:
        profile = KycProfile(
            provider=provider,
            title=title,
            source_url=source_url,
            source_updated_at=source_updated_at,
            fetched_at=fetched_at or datetime.now(UTC),
        )
        self.db.add(profile)
        self.db.flush()

        for level in levels:
            self.db.add(
                KycLevel(
                    kyc_profile_id=profile.id,
                    level_name=level["level_name"],
                    rank=level["rank"],
                    description=level.get("description"),
                    limit_reference=level.get("limit_reference"),
                    exchange_limit_text=level.get("exchange_limit_text"),
                    exchange_limit_period=level.get("exchange_limit_period"),
                    fiat_deposit_limit=level.get("fiat_deposit_limit"),
                    fiat_withdrawal_limit=level.get("fiat_withdrawal_limit"),
                    crypto_deposit_limit=level.get("crypto_deposit_limit"),
                    crypto_withdrawal_limit=level.get("crypto_withdrawal_limit"),
                    requirements=level.get("requirements", []),
                    notes=level.get("notes"),
                    metadata_json=level.get("metadata_json"),
                )
            )

        self.db.commit()
        self.db.refresh(profile)
        return profile

    def create_profile_with_levels(
        self,
        *,
        provider: ProviderName,
        source_url: str,
        fetch_run: FetchRun,
        raw_record: RawRecord,
        kyc_document: dict,
    ) -> int:
        profile = KycProfile(
            provider=provider,
            title=kyc_document["title"] or "KYC profile",
            source_url=source_url,
            source_updated_at=kyc_document.get("updated_at"),
            fetched_at=datetime.now(UTC),
            fetch_run_id=fetch_run.id,
            raw_record_id=raw_record.id,
        )
        self.db.add(profile)
        self.db.flush()

        created = 0
        for index, level in enumerate(kyc_document.get("levels", []), start=1):
            self.db.add(
                KycLevel(
                    kyc_profile_id=profile.id,
                    level_name=level["level_name"],
                    rank=index,
                    description=level.get("description"),
                    limit_reference=level.get("limit_reference"),
                    exchange_limit_text=level.get("exchange_limit_text"),
                    exchange_limit_period=level.get("exchange_limit_period"),
                    fiat_deposit_limit=level.get("fiat_deposit_limit"),
                    fiat_withdrawal_limit=level.get("fiat_withdrawal_limit"),
                    crypto_deposit_limit=level.get("crypto_deposit_limit"),
                    crypto_withdrawal_limit=level.get("crypto_withdrawal_limit"),
                    requirements=level.get("requirements", []),
                    notes=level.get("notes"),
                    metadata_json=level.get("metadata_json"),
                )
            )
            created += 1

        self.db.commit()
        return created
