from __future__ import annotations

import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from app.adapters.crypto.busha import BushaAdapter
from app.adapters.crypto.quidax import QuidaxAdapter
from app.core.database import SessionLocal
from app.repositories.asset import AssetRepository
from app.repositories.provider_asset import ProviderAssetRepository
from app.services.ingestion.bootstrap import BootstrapIngestionService
from app.services.ingestion.focus import FocusAssetSelector


async def run() -> None:
    db = SessionLocal()
    try:
        service = BootstrapIngestionService(
            asset_repository=AssetRepository(db),
            provider_asset_repository=ProviderAssetRepository(db),
            quidax_adapter=QuidaxAdapter(),
            busha_adapter=BushaAdapter(),
            focus_selector=FocusAssetSelector(),
        )
        result = await service.run()
        print(result)
    finally:
        db.close()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
