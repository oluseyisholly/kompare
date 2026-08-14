from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.item import Item
from app.repositories.base import BaseRepository


class ItemRepository(BaseRepository[Item]):
    def __init__(self, db: Session) -> None:
        super().__init__(db=db, model=Item)


def get_item_repository(db: Session = Depends(get_db)) -> ItemRepository:
    return ItemRepository(db=db)
