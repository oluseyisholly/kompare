from sqlalchemy.orm import Session

from app.models.item import Item
from app.services.base import BaseService


class ItemService(BaseService):
    def __init__(self, db: Session):
        super().__init__(db=db, model=Item)
