from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.repositories.mutual_fund import MutualFundRepository
from app.schemas.common import ApiResponse, PaginatedData
from app.schemas.mutual_fund import MutualFundRead, MutualFundSnapshotRead
from app.services.mutual_fund import MutualFundService

router = APIRouter(prefix="/mutual-funds", tags=["mutual-funds"])


def get_mutual_fund_service(db: Session = Depends(get_db)):
    return MutualFundService(MutualFundRepository(db))


@router.get("/", response_model=ApiResponse[PaginatedData[MutualFundRead]])
def list_funds(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    provider: str | None = Query(default=None, examples=["stanbic"]),
    service: MutualFundService = Depends(get_mutual_fund_service),
):
    return service.list_funds(page=page, per_page=per_page, provider_slug=provider)


@router.get("/{code}/latest-snapshot", response_model=ApiResponse[MutualFundSnapshotRead])
def latest_snapshot(
    code: str = Path(
        examples=["stanbic-simm"],
        description="Stable fund code returned by the fund listing endpoint.",
    ),
    service: MutualFundService = Depends(get_mutual_fund_service),
):
    return service.latest_snapshot(code)
