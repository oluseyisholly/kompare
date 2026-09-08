from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from app.adapters.giftcard.cardtonic import CardtonicAdapter
from app.core.database import SessionLocal
from app.repositories.asset import AssetRepository
from app.repositories.fetch_run import FetchRunRepository
from app.repositories.giftcard_rate import GiftCardRateRepository
from app.repositories.giftcard_variant import GiftCardVariantRepository
from app.repositories.provider import ProviderRepository
from app.repositories.raw_record import RawRecordRepository
from app.repositories.kyc import KycRepository
from app.services.ingestion.cardtonic import CardtonicIngestionService


async def run(include_top_cards: bool, kyc_only: bool = False) -> None:
    db = SessionLocal()
    try:
        service = CardtonicIngestionService(
            db=db,
            adapter=CardtonicAdapter(),
            asset_repository=AssetRepository(db),
            provider_repository=ProviderRepository(db),
            fetch_run_repository=FetchRunRepository(db),
            raw_record_repository=RawRecordRepository(db),
            giftcard_variant_repository=GiftCardVariantRepository(db),
            giftcard_rate_repository=GiftCardRateRepository(db),
            kyc_repository=KycRepository(db),
        )
        result = await service.ingest_kyc() if kyc_only else await service.ingest(include_top_cards=include_top_cards)
        print(result)
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Cardtonic gift card ingestion.")
    parser.add_argument("--kyc-only", action="store_true", help="Fetch only Cardtonic KYC requirements.")
    parser.add_argument(
        "--skip-top-cards",
        action="store_true",
        help="Skip fetching the top cards endpoint.",
    )
    args = parser.parse_args()
    asyncio.run(run(include_top_cards=not args.skip_top_cards, kyc_only=args.kyc_only))


if __name__ == "__main__":
    main()
