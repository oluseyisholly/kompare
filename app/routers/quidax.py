from fastapi import APIRouter, Depends, Query

from app.dependencies import get_quidax_service
from app.schemas.common import ApiResponse, PaginatedData
from app.schemas.quidax import QuidaxMarketRead
from app.services.quidax import QuidaxService

router = APIRouter(prefix="/quidax", tags=["quidax"])


@router.get("/markets", response_model=ApiResponse[PaginatedData[QuidaxMarketRead]])
async def get_quidax_markets(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    service: QuidaxService = Depends(get_quidax_service),
) -> ApiResponse[PaginatedData[QuidaxMarketRead]]:
    return await service.get_markets(page=page, per_page=per_page)
