from fastapi import Depends

from app.core.database import get_db
from app.repositories.item import ItemRepository, get_item_repository
from app.services.base import BaseService


class ItemService(BaseService):
    def __init__(self, repository: ItemRepository) -> None:
        super().__init__(repository=repository)


def get_item_service(repository: ItemRepository = Depends(get_item_repository)) -> ItemService:
    return ItemService(repository=repository)
