from fastapi import APIRouter, Depends, Query

from app.dependencies import get_busha_service
from app.schemas.busha import BushaPairRead
from app.schemas.common import ApiResponse, PaginatedData
from app.services.busha import BushaService

router = APIRouter(prefix="/busha", tags=["busha"])


@router.get("/pairs", response_model=ApiResponse[PaginatedData[BushaPairRead]])
async def get_busha_pairs(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    service: BushaService = Depends(get_busha_service),
) -> ApiResponse[PaginatedData[BushaPairRead]]:
    return await service.get_pairs(page=page, per_page=per_page)
