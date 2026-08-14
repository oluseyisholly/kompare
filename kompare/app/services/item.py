from sqlalchemy.orm import Session

from models.item import Item
from services.base import BaseService


class ItemService(BaseService):
    def __init__(self, db: Session):
        super().__init__(db=db, model=Item)