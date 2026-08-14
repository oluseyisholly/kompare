from __future__ import annotations

from typing import Generic, List, Type, TypeVar

from sqlalchemy.inspection import inspect
from sqlalchemy.orm import Session
from sqlalchemy.sql import text

ModelType = TypeVar("ModelType")


class BaseRepository(Generic[ModelType]):
    def __init__(self, db: Session, model: Type[ModelType]) -> None:
        self.db = db
        self.model = model
        self.pk_name = self._get_primary_key_name()

    def _get_primary_key_name(self) -> str:
        mapper = inspect(self.model)
        pk_columns = [key.name for key in mapper.primary_key]
        if not pk_columns:
            raise ValueError(f"Model {self.model.__name__} has no primary key defined")
        return pk_columns[0]

    def create(self, data: dict) -> ModelType:
        entity = self.model(**data)
        self.db.add(entity)
        self.db.commit()
        self.db.refresh(entity)
        return entity

    def list(self, order_by: str | None = None) -> List[ModelType]:
        order_by = text(self.pk_name) if order_by is None else text(order_by)
        return self.db.query(self.model).order_by(order_by).all()

    def count(self) -> int:
        return self.db.query(self.model).count()

    def paginate(
        self,
        skip: int = 0,
        limit: int = 10,
        order_by: str | None = None,
    ) -> tuple[List[ModelType], int]:
        order_by = text(self.pk_name) if order_by is None else text(order_by)
        query = self.db.query(self.model).order_by(order_by)
        total = query.count()
        items = query.offset(skip).limit(limit).all()
        return items, total

    def get(self, entity_id: int) -> ModelType | None:
        primary_key_field = getattr(self.model, self.pk_name)
        return self.db.query(self.model).filter(primary_key_field == entity_id).first()

    def update(self, entity_id: int, data: dict) -> ModelType | None:
        primary_key_field = getattr(self.model, self.pk_name)
        entity = self.db.query(self.model).filter(primary_key_field == entity_id).first()
        if not entity:
            return None

        for key, value in data.items():
            setattr(entity, key, value)

        self.db.commit()
        self.db.refresh(entity)
        return entity

    def delete(self, entity_id: int) -> ModelType | None:
        primary_key_field = getattr(self.model, self.pk_name)
        entity = self.db.query(self.model).filter(primary_key_field == entity_id).first()
        if not entity:
            return None

        self.db.delete(entity)
        self.db.commit()
        return entity
