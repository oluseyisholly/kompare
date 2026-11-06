import argparse
import asyncio

from app.core.database import SessionLocal
from app.services.ingestion.wise import WiseIngestionService


async def main(job_type="market_data"):
    with SessionLocal() as db:
        service = WiseIngestionService(db)
        method = (
            service.ingest_currencies if job_type == "currencies" else service.ingest_market_data
        )
        print(await method())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest authenticated Wise reference rates")
    parser.add_argument("--job-type", choices=["market_data", "currencies"], default="market_data")
    asyncio.run(main(parser.parse_args().job_type))
