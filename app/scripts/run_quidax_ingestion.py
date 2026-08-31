from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from app.core.database import SessionLocal
from app.repositories.fetch_run import FetchRunRepository
from app.repositories.kyc import KycRepository
from app.repositories.provider_asset import ProviderAssetRepository
from app.repositories.quote import QuoteRepository
from app.repositories.raw_record import RawRecordRepository
from app.adapters.crypto.quidax import QuidaxAdapter
from app.services.ingestion import QuidaxIngestionService


async def run(include_kyc: bool) -> None:
    db = SessionLocal()
    try:
        service = QuidaxIngestionService(
            db=db,
            adapter=QuidaxAdapter(),
            fetch_run_repository=FetchRunRepository(db),
            raw_record_repository=RawRecordRepository(db),
            provider_asset_repository=ProviderAssetRepository(db),
            quote_repository=QuoteRepository(db),
            kyc_repository=KycRepository(db),
        )
        result = await service.ingest(include_kyc=include_kyc)
        print(result)
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Quidax ingestion.")
    parser.add_argument(
        "--skip-kyc",
        action="store_true",
        help="Skip scraping the Quidax KYC support page.",
    )
    args = parser.parse_args()
    asyncio.run(run(include_kyc=not args.skip_kyc))


if __name__ == "__main__":
    main()
