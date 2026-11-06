import argparse
import asyncio

from app.core.database import SessionLocal
from app.models.enums import IngestionJobType
from app.services.ingestion.fx import FX_INGESTION_SERVICES, run_fx_ingestion


async def main(provider, job_type):
    with SessionLocal() as db:
        print(await run_fx_ingestion(db, provider=provider, job_type=IngestionJobType(job_type)))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Harvest FX data using a registered provider adapter"
    )
    parser.add_argument("--provider", choices=sorted(FX_INGESTION_SERVICES), required=True)
    parser.add_argument("--job-type", choices=["market_data", "currencies"], default="market_data")
    arguments = parser.parse_args()
    asyncio.run(main(arguments.provider, arguments.job_type))
