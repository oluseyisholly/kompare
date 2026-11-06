import argparse
import asyncio

from app.core.database import SessionLocal
from app.services.ingestion.stanbic import StanbicIngestionService


async def main(job_type="market_data"):
    with SessionLocal() as db:
        service = StanbicIngestionService(db)
        method = (
            service.ingest_fund_details
            if job_type == "fund_details"
            else service.ingest_market_data
        )
        print(await method())


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--job-type", choices=("market_data", "fund_details"), default="market_data"
    )
    asyncio.run(main(parser.parse_args().job_type))
