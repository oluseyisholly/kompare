from fastapi import APIRouter, Depends, Query

from app.schemas.item import ItemCreate, ItemPage, ItemRead
from app.services.item import ItemService, get_item_service

router = APIRouter(prefix="/items", tags=["items"])


@router.post("/", response_model=ItemRead)
def create_item(item: ItemCreate, service: ItemService = Depends(get_item_service)):
    return service.create_item(item)


@router.get("/", response_model=ItemPage)
def list_items(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    service: ItemService = Depends(get_item_service),
):
    return service.paginate_items(skip=skip, limit=limit)


@router.get("/{item_id}", response_model=ItemRead)
def read_item(item_id: int, service: ItemService = Depends(get_item_service)):
    return service.get_item(item_id)
