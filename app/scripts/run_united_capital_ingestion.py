import argparse
import asyncio

from app.core.database import SessionLocal
from app.services.ingestion.united_capital import UnitedCapitalIngestionService


async def main(job_type="market_data", fund_code=None):
    with SessionLocal() as db:
        service = UnitedCapitalIngestionService(db)
        result = (
            await service.ingest_fund_details(fund_code=fund_code)
            if job_type == "fund_details"
            else await service.ingest_market_data()
        )
        print(result)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--job-type", choices=("market_data", "fund_details"), default="market_data"
    )
    parser.add_argument("--fund-code", help="Optional fund code for a details-only run")
    args = parser.parse_args()
    if args.fund_code and args.job_type != "fund_details":
        parser.error("--fund-code requires --job-type fund_details")
    asyncio.run(main(args.job_type, args.fund_code))
