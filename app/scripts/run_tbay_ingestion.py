"""Run with python3 -m app.scripts.run_tbay_ingestion."""
import asyncio

from app.core.database import SessionLocal
from app.dependencies.providers import build_tbay_ingestion_service


async def run():
    with SessionLocal() as db:
        print(await build_tbay_ingestion_service(db).ingest())


if __name__ == "__main__":
    asyncio.run(run())
